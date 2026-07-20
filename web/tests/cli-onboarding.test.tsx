import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import HomePage from "../app/page";
import SubmitPage from "../app/submit/page";
import {
  CLI_PREREQUISITES,
  LOCALBENCH_INSTALL_COMMAND,
  LOCALBENCH_TESTED_VERSION,
} from "../lib/cli-onboarding";

describe("CLI onboarding cross-surface contract", () => {
  it("renders the same install version and prerequisites on landing and submit pages", async () => {
    const landing = renderToStaticMarkup(await HomePage());
    const submit = renderToStaticMarkup(<SubmitPage />);

    for (const prerequisite of CLI_PREREQUISITES) {
      expect(landing).toContain(prerequisite);
      expect(submit).toContain(prerequisite);
    }
    expect(landing).toContain(LOCALBENCH_INSTALL_COMMAND.replaceAll('"', "&quot;"));
    expect(submit).toContain(LOCALBENCH_INSTALL_COMMAND.replaceAll('"', "&quot;"));
    expect(landing).toContain(`Tested with local-bench-ai ${LOCALBENCH_TESTED_VERSION}`);
    expect(submit).toContain(`Tested with local-bench-ai ${LOCALBENCH_TESTED_VERSION}`);
  });
});
