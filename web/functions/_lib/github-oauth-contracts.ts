import { z } from "zod";

export const GITHUB_OAUTH_CLIENT_ID = "Ov23liGbCyw1WtlJ0jmj";
export const GITHUB_OAUTH_CALLBACK_URL = "https://local-bench.ai/api/auth/github/callback";

const Hex32Schema = z.string().regex(/^[0-9a-f]{32}$/u);
const Ed25519PublicKeySchema = z.string().regex(/^[0-9a-f]{64}$/u);
const Ed25519SignatureSchema = z.string().regex(/^[0-9a-f]{128}$/u);
const GithubLoginSchema = z.string().min(1).max(40).regex(/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}[A-Za-z0-9])?$/u);

export const GithubDevicePollRequestSchema = z.object({
  device_code_handle: z.templateLiteral(["dch_", Hex32Schema]),
  pop: z.object({
    signature: Ed25519SignatureSchema,
    timestamp: z.string().min(1).max(40),
  }).strict(),
  public_key: Ed25519PublicKeySchema,
}).strict();

export const GithubDeviceCodeResponseSchema = z.object({
  device_code: z.string().min(1).max(200),
  expires_in: z.number().int().min(1).max(3600),
  interval: z.number().int().min(1).max(60),
  user_code: z.string().min(1).max(40),
  verification_uri: z.string().url().max(200),
}).strict();

export const GithubTokenResponseSchema = z.union([
  z.object({ access_token: z.string().min(1).max(500), scope: z.string(), token_type: z.string() }).passthrough(),
  z.object({ error: z.string().min(1).max(80), interval: z.number().int().min(1).max(120).optional() }).passthrough(),
]);

export const GithubUserSchema = z.object({
  id: z.number().int().nonnegative().safe(),
  login: GithubLoginSchema,
}).passthrough();

export type GithubDevicePollRequest = z.infer<typeof GithubDevicePollRequestSchema>;
export type GithubUser = z.infer<typeof GithubUserSchema>;
