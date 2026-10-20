import { readFileSync } from "node:fs";
import type { ExtensionAPI, ProviderConfig } from "@earendil-works/pi-coding-agent";

// Pi discovers project extensions, but models.json normally lives in its agent directory.
export default function (pi: ExtensionAPI) {
  const config = JSON.parse(
    readFileSync(new URL("../models.json", import.meta.url), "utf8"),
  ) as { providers: { llamacpp: ProviderConfig } };
  pi.registerProvider("llamacpp", config.providers.llamacpp);
}
