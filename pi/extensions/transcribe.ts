import { spawn } from "node:child_process";
import { access, mkdir, mkdtemp, realpath, rm, stat } from "node:fs/promises";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { homedir } from "node:os";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { stopTree } from "./process-tree.ts";

type PpsResult = {
  type: "result";
  schema: string;
  artifacts: { document: string; transcript: string; html: string; markdown: string };
  source: string;
  duration_seconds: number;
  elapsed_seconds: number;
  counts: { cues: number; sections: number; stills: number };
  provenance: Record<string, unknown>;
  index: Array<{ start_seconds: number; timestamp: string; excerpt: string }>;
  index_truncated: boolean;
};

type RunOptions = {
  input: string;
  output?: string;
  cwd: string;
  signal?: AbortSignal;
  update?: (phase: string) => void;
};

function requiredAbsolutePath(name: string): string {
  const value = process.env[name];
  if (!value || !isAbsolute(value)) {
    throw new Error(`${name} must be an absolute path`);
  }
  return value;
}

async function localFile(raw: string, cwd: string): Promise<string> {
  const value = raw.startsWith("@") ? raw.slice(1) : raw;
  if (/^[a-z]+:\/\//i.test(value)) throw new Error("Only local files are supported");
  const path = await realpath(resolve(cwd, value));
  if (!(await stat(path)).isFile()) throw new Error(`Recording is not a file: ${path}`);
  return path;
}

async function runPps(options: RunOptions): Promise<PpsResult> {
  let output: string | undefined;
  let terminate: (() => Promise<void>) | undefined;
  let abort: (() => void) | undefined;
  let stopping: Promise<void> | undefined;
  try {
    options.signal?.throwIfAborted();
    options.update?.("checking");
    const executable = requiredAbsolutePath("PPS_EXECUTABLE");
    await access(executable);
    const input = await localFile(options.input, options.cwd);
    const cache = process.env.PPS_MODEL_PATH || requiredAbsolutePath("PPS_MODEL_CACHE");
    if (!isAbsolute(cache)) throw new Error("PPS_MODEL_PATH must be an absolute path");
    await access(cache);
    options.signal?.throwIfAborted();

    if (options.output) {
      const destination = resolve(options.cwd, options.output);
      await mkdir(dirname(destination), { recursive: true });
      await mkdir(destination);
      output = destination;
    } else {
      const root = process.env.PPS_OUTPUT_ROOT || join(homedir(), ".local", "share", "podleparsesskewl", "runs");
      if (!isAbsolute(root)) throw new Error("PPS_OUTPUT_ROOT must be an absolute path");
      await mkdir(root, { recursive: true });
      output = await mkdtemp(join(root, "transcription-"));
    }

    const args = [
      "transcribe", input, "--output", output, "--offline-transcription",
      "--jsonl-progress", "--device", process.env.PPS_DEVICE || "auto",
    ];
    if (process.env.PPS_MODEL_PATH) args.push("--whisper-model-path", cache);
    else args.push("--local-files-root", cache, "--whisper-model", process.env.PPS_MODEL || "base");

    options.signal?.throwIfAborted();
    const child = spawn(executable, args, {
      cwd: options.cwd,
      detached: process.platform !== "win32",
      shell: false,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    const closed = new Promise<number | null>((done, reject) => {
      child.once("error", reject);
      child.once("close", done);
    });
    terminate = () => stopping ??= stopTree(child);
    let stdout = "";
    let stderr = "";
    let result: PpsResult | undefined;
    const consume = (chunk: string) => {
      stdout += chunk;
      const lines = stdout.split("\n");
      stdout = lines.pop() || "";
      for (const line of lines) {
        try {
          const event = JSON.parse(line);
          if (event.type === "progress") options.update?.(event.phase);
          if (event.type === "result") result = event as PpsResult;
        } catch {
          stderr = `${stderr}\n${line}`.slice(-20000);
        }
      }
    };
    child.stdout?.setEncoding("utf8").on("data", consume);
    child.stderr?.setEncoding("utf8").on("data", (chunk: string) => { stderr = (stderr + chunk).slice(-20000); });
    abort = () => { void terminate!(); };
    options.signal?.addEventListener("abort", abort, { once: true });
    if (options.signal?.aborted) abort();

    const code = await closed;
    if (stdout) consume("\n");
    await stopping;
    options.signal?.throwIfAborted();
    if (code !== 0) throw new Error(`PPS transcription failed (${code}): ${stderr.trim() || "no diagnostics"}`);
    if (!result || result.schema !== "podleparsesskewl.transcription/v1") {
      throw new Error("PPS did not return a valid transcription result");
    }
    for (const path of Object.values(result.artifacts)) await access(path);
    options.signal?.throwIfAborted();
    return result;
  } catch (error) {
    await terminate?.();
    if (output) await rm(output, { recursive: true, force: true });
    throw error;
  } finally {
    await stopping;
    if (abort) options.signal?.removeEventListener("abort", abort);
  }
}

function boundedResult(result: PpsResult): string {
  return JSON.stringify(result, null, 2);
}

export default function (pi: ExtensionAPI) {
  let active: { controller: AbortController; done: Promise<PpsResult> } | undefined;
  async function run(options: RunOptions): Promise<PpsResult> {
    if (active) throw new Error("A PPS transcription is already running in this Pi session");
    const controller = new AbortController();
    const done = Promise.resolve().then(() => runPps({
      ...options,
      signal: options.signal ? AbortSignal.any([controller.signal, options.signal]) : controller.signal,
    }));
    active = { controller, done };
    try {
      return await done;
    } finally {
      active = undefined;
    }
  }

  pi.registerShortcut("ctrl+shift+x", {
    description: "Cancel the active PPS transcription",
    handler: async () => { active?.controller.abort(); },
  });
  pi.registerTool({
    name: "pps_transcribe",
    label: "Transcribe local media",
    description: "Transcribe a local audio/video file with offline PodleParsesSkewl. Returns bounded artifact paths, counts, timing, provenance, and a short index. The full transcript stays on disk.",
    promptSnippet: "Transcribe long local audio/video to local artifacts without returning the full transcript",
    promptGuidelines: [
      "Use pps_transcribe for local long-video transcription and open only the returned local artifacts needed for the user's task.",
    ],
    parameters: Type.Object({
      path: Type.String({ description: "Local media path, resolved from the current project" }),
      output: Type.Optional(Type.String({ description: "New output directory; defaults to a unique temporary directory" })),
    }),
    async execute(_id, params, signal, onUpdate, ctx) {
      const result = await run({
        input: params.path,
        output: params.output,
        cwd: ctx.cwd,
        signal,
        update: (phase) => onUpdate?.({ content: [{ type: "text", text: `${phase} local media...` }], details: { phase } }),
      });
      return { content: [{ type: "text", text: boundedResult(result) }], details: result };
    },
  });

  pi.registerCommand("transcribe", {
    description: "Transcribe one explicit local audio/video path with PPS",
    handler: async (args, ctx) => {
      if (args.trim() === "--cancel") {
        active?.controller.abort();
        return;
      }
      const input = args.trim().replace(/^(["'])(.*)\1$/, "$2");
      if (!input) {
        if (ctx.hasUI) ctx.ui.notify("Usage: /transcribe <local-path> (Ctrl+Shift+X or /transcribe --cancel to cancel)", "warning");
        return;
      }
      try {
        if (ctx.hasUI) ctx.ui.setStatus("pps-transcribe", "checking local media...");
        const result = await run({
          input,
          cwd: ctx.cwd,
          signal: ctx.signal,
          update: (phase) => { if (ctx.hasUI) ctx.ui.setStatus("pps-transcribe", `${phase} local media...`); },
        });
        pi.appendEntry("pps-transcription", result);
        if (ctx.hasUI) ctx.ui.notify(`Transcript: ${result.artifacts.transcript}`, "info");
      } catch (error) {
        if (ctx.hasUI) ctx.ui.notify(error instanceof Error ? error.message : String(error), "error");
      } finally {
        if (ctx.hasUI) ctx.ui.setStatus("pps-transcribe", undefined);
      }
    },
  });

  pi.on("session_shutdown", async () => {
    const job = active;
    job?.controller.abort();
    await job?.done.catch(() => {});
  });
}
