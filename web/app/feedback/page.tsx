"use client";

import { useMemo, useState } from "react";

const MESSAGE_MIN = 10;
const MESSAGE_MAX = 4000;
const CONTACT_MAX = 200;

type SubmitState = "idle" | "submitting" | "success" | "error";

export default function FeedbackPage() {
  const [message, setMessage] = useState("");
  const [contact, setContact] = useState("");
  const [state, setState] = useState<SubmitState>("idle");
  const [error, setError] = useState<string | null>(null);
  const trimmedMessage = message.trim();
  const canSubmit = trimmedMessage.length >= MESSAGE_MIN && trimmedMessage.length <= MESSAGE_MAX && contact.length <= CONTACT_MAX;
  const counterTone = useMemo(() => {
    if (trimmedMessage.length > MESSAGE_MAX || trimmedMessage.length < MESSAGE_MIN) {
      return "text-bench-warn-soft";
    }
    return "text-bench-muted";
  }, [trimmedMessage.length]);

  async function submitFeedback(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit || state === "submitting") {
      return;
    }
    setState("submitting");
    setError(null);
    const response = await fetch("/api/feedback", {
      body: JSON.stringify({ contact: contact.trim(), message: trimmedMessage }),
      headers: { "content-type": "application/json" },
      method: "POST",
    });
    if (response.ok) {
      setState("success");
      setMessage("");
      setContact("");
      return;
    }
    let code = "feedback_failed";
    try {
      const payload: unknown = await response.json();
      if (typeof payload === "object" && payload !== null && "code" in payload && typeof payload.code === "string") {
        code = payload.code;
      }
    } catch {
      code = "feedback_failed";
    }
    setError(code === "rate_limited" ? "Rate limit reached. Try again later." : "Feedback could not be submitted.");
    setState("error");
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-7 px-5 py-8 lg:px-8">
      <header className="border-b border-bench-line pb-5">
        <p className="font-mono text-xs font-semibold uppercase tracking-wide text-bench-accent">feedback</p>
        <h1 className="mt-2 text-4xl font-semibold text-bench-text">Feedback</h1>
        <p className="mt-3 max-w-2xl leading-7 text-bench-muted">
          This goes to the maintainer. No account is created. Do not include secrets, API keys, private model paths, or
          anything that should not be stored as plain text.
        </p>
      </header>

      {state === "success" ? (
        <section className="rounded-lg border border-bench-line bg-bench-panel p-5">
          <h2 className="text-xl font-semibold text-bench-text">Sent</h2>
          <p className="mt-2 leading-7 text-bench-muted">
            Thanks. You can also open an issue or discussion in the{" "}
            <a href="https://github.com/local-bench/local-bench" className="text-bench-accent hover:underline" target="_blank" rel="noreferrer">
              GitHub repo
            </a>
            .
          </p>
          <button
            type="button"
            className="mt-4 rounded border border-bench-line px-3 py-2 text-sm font-semibold text-bench-text hover:border-bench-accent"
            onClick={() => setState("idle")}
          >
            Send another
          </button>
        </section>
      ) : (
        <form className="rounded-lg border border-bench-line bg-bench-panel p-5" onSubmit={submitFeedback}>
          <label className="block text-sm font-semibold text-bench-text" htmlFor="feedback-message">
            Message
          </label>
          <textarea
            id="feedback-message"
            minLength={MESSAGE_MIN}
            maxLength={MESSAGE_MAX}
            required
            className="mt-2 min-h-[220px] w-full resize-y rounded border border-bench-line bg-bench-panel-2 px-3 py-2 text-sm leading-6 text-bench-text outline-none focus:border-bench-accent"
            value={message}
            onChange={(event) => setMessage(event.currentTarget.value)}
          />
          <div className={`mt-1 text-right font-mono text-[11px] ${counterTone}`}>
            {trimmedMessage.length}/{MESSAGE_MAX}
          </div>

          <label className="mt-4 block text-sm font-semibold text-bench-text" htmlFor="feedback-contact">
            How can we reach you? <span className="font-normal text-bench-muted">(optional)</span>
          </label>
          <input
            id="feedback-contact"
            maxLength={CONTACT_MAX}
            className="mt-2 w-full rounded border border-bench-line bg-bench-panel-2 px-3 py-2 text-sm text-bench-text outline-none focus:border-bench-accent"
            value={contact}
            onChange={(event) => setContact(event.currentTarget.value)}
          />
          <div className="mt-1 text-right font-mono text-[11px] text-bench-muted">{contact.length}/{CONTACT_MAX}</div>

          {error === null ? null : <p className="mt-3 text-sm text-bench-warn-soft">{error}</p>}
          <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-bench-muted">
              Prefer public discussion? Use the{" "}
              <a href="https://github.com/local-bench/local-bench" className="text-bench-accent hover:underline" target="_blank" rel="noreferrer">
                GitHub repo
              </a>
              .
            </p>
            <button
              type="submit"
              disabled={!canSubmit || state === "submitting"}
              className="rounded border border-bench-accent bg-bench-accent px-4 py-2 text-sm font-semibold text-bench-bg disabled:cursor-not-allowed disabled:border-bench-line disabled:bg-bench-muted disabled:text-bench-bg/70"
            >
              {state === "submitting" ? "Sending..." : "Send feedback"}
            </button>
          </div>
        </form>
      )}
    </main>
  );
}
