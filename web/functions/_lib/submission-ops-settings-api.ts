import { OpsSettingsUpdateSchema, type SubmissionApiEnv } from "./submission-contracts";
import { adminBlocked, jsonResponse } from "./submission-api-support";

type OpsSetting = {
  readonly disabled_by: string | null;
  readonly key: string;
  readonly updated_at: string;
  readonly value: string;
};

export async function handleGetOpsSettings(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const blocked = adminBlocked(request, env);
  if (blocked !== null) {
    return blocked;
  }
  return jsonResponse(200, { settings: await listSettings(env) });
}

export async function handleUpdateOpsSettings(request: Request, env: SubmissionApiEnv): Promise<Response> {
  const blocked = adminBlocked(request, env);
  if (blocked !== null) {
    return blocked;
  }
  const parsed = OpsSettingsUpdateSchema.safeParse(await request.json());
  if (!parsed.success) {
    return jsonResponse(400, { code: "invalid_ops_setting", error: "invalid ops setting update" });
  }
  const current = await autoPublishSetting(env);
  if (parsed.data.value === "on" && ownerLocked(current.disabled_by) && parsed.data.actor !== "owner") {
    return jsonResponse(403, {
      code: "kill_switch_owner_only",
      error: "auto_publish can only be re-enabled by the owner after owner/security disable",
    });
  }
  if (parsed.data.value === "off") {
    await env.DB.prepare(
      `insert into ops_settings (key, value, disabled_by, updated_at)
       values ('auto_publish', 'off', ?, datetime('now'))
       on conflict(key) do update set value = 'off', disabled_by = excluded.disabled_by, updated_at = datetime('now')`,
    )
      .bind(parsed.data.actor)
      .run();
  } else {
    await env.DB.prepare(
      `insert into ops_settings (key, value, disabled_by, updated_at)
       values ('auto_publish', 'on', null, datetime('now'))
       on conflict(key) do update set value = 'on', disabled_by = null, updated_at = datetime('now')`,
    ).run();
  }
  return jsonResponse(200, await autoPublishSetting(env));
}

async function listSettings(env: SubmissionApiEnv): Promise<readonly OpsSetting[]> {
  const rows = await env.DB.prepare("select key, value, disabled_by, updated_at from ops_settings order by key").all();
  return rows.results.map(settingRow);
}

async function autoPublishSetting(env: SubmissionApiEnv): Promise<OpsSetting> {
  const row = await env.DB.prepare("select key, value, disabled_by, updated_at from ops_settings where key = 'auto_publish'").first();
  if (row === null) {
    await env.DB.prepare(
      "insert into ops_settings (key, value, disabled_by, updated_at) values ('auto_publish', 'off', null, datetime('now'))",
    ).run();
    return autoPublishSetting(env);
  }
  return settingRow(row);
}

function settingRow(row: Record<string, unknown>): OpsSetting {
  return {
    disabled_by: nullableText(row, "disabled_by"),
    key: text(row, "key"),
    updated_at: text(row, "updated_at"),
    value: text(row, "value"),
  };
}

function ownerLocked(disabledBy: string | null): boolean {
  return disabledBy === "owner" || disabledBy === "security";
}

function text(row: Record<string, unknown>, key: string): string {
  const value = row[key];
  if (typeof value !== "string") {
    throw new Error(`ops_settings.${key} must be a string`);
  }
  return value;
}

function nullableText(row: Record<string, unknown>, key: string): string | null {
  const value = row[key];
  if (value === null || typeof value === "string") {
    return value;
  }
  throw new Error(`ops_settings.${key} must be a string or null`);
}
