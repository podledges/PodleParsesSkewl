import assert from "node:assert/strict";
import { createRequire, registerHooks } from "node:module";
import { pathToFileURL } from "node:url";
import { mkdtemp, writeFile, readFile, access, rm } from "node:fs/promises";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import test from "node:test";

const require = createRequire(import.meta.url);
const typeboxUrl = pathToFileURL(require.resolve("typebox")).href;
registerHooks({
  resolve(specifier, context, next) {
    if (specifier === "typebox") return next(typeboxUrl, context);
    return next(specifier, context);
  },
});
const { default: extension } = await import("../pi/extensions/transcribe.ts");

function session(cwd) {
  const handlers = {};
  const commands = {};
  const shortcuts = {};
  let tool;
  extension({
    registerTool(value) { tool = value; },
    registerCommand(name, value) { commands[name] = value; },
    registerShortcut(name, value) { shortcuts[name] = value; },
    on(name, handler) { handlers[name] = handler; },
    appendEntry() {},
  });
  return {
    run(output, signal, update, path = "hang.mp3") {
      return tool.execute("test", { path, output }, signal, update, { cwd });
    },
    shutdown: handlers.session_shutdown,
    command: (input, ctx = {}) => commands.transcribe.handler(input, { cwd, hasUI: false, ...ctx }),
    cancel: () => shortcuts["ctrl+shift+x"].handler(),
  };
}

async function absent(path) {
  await assert.rejects(access(path), { code: "ENOENT" });
}

async function waitFor(path) {
  for (let i = 0; i < 200; i++) {
    try { return await readFile(path, "utf8"); } catch {}
    await delay(10);
  }
  throw new Error(`Timed out waiting for ${path}`);
}

test("registered PPS tool and command own jobs until teardown and preserve artifacts", { timeout: 20000, skip: process.platform === "win32" }, async () => {
  const root = await mkdtemp(join(process.cwd(), ".bridge-test-"));
  const saved = { ...process.env };
  try {
    const executable = join(root, "pps.mjs");
    await writeFile(executable, `#!/usr/bin/env node
import { spawn } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
const output = process.argv[process.argv.indexOf('--output') + 1];
if (process.argv[3].endsWith('success.mp3')) {
  const artifact = join(output, 'é-transcript.md');
  writeFileSync(artifact, 'private transcript');
  const result = JSON.stringify({type:'result', schema:'podleparsesskewl.transcription/v1', source:process.argv[3], artifacts:{transcript:artifact}});
  spawn(process.execPath, ['-e', \
    'const b=Buffer.from(process.argv[1]); const i=b.indexOf(Buffer.from("é"))+1; setTimeout(()=>{process.stdout.write(b.subarray(0,i));setTimeout(()=>process.stdout.write(b.subarray(i)),30)},60)', result],
    {stdio:['ignore', 'inherit', 'inherit']});
  process.exit(0);
} else {
  const child = spawn(process.execPath, ['-e', \
    'process.on("SIGTERM",()=>{}); console.log(process.pid); setInterval(()=>{},1000)'],
    {stdio:['ignore','pipe','inherit']});
  child.stdout.once('data', data => {
    writeFileSync(join(output,'pid'), data);
    console.log(JSON.stringify({type:'progress',phase:'processing'}));
  });
  setInterval(()=>{},1000);
}
`, { mode: 0o755 });
    await writeFile(join(root, "hang.mp3"), "audio");
    await writeFile(join(root, "success.mp3"), "audio");
    await writeFile(join(root, "@success.mp3"), "different audio");
    process.env.PPS_EXECUTABLE = executable;
    process.env.PPS_MODEL_CACHE = root;
    delete process.env.PPS_MODEL_PATH;
    process.env.PPS_OUTPUT_ROOT = join(root, "runs");

    const a = session(root);
    const b = session(root);
    const controller = new AbortController();
    const output = join(root, "owned");
    const first = a.run(output, controller.signal);
    const rejected = assert.rejects(first, /abort/i);
    await assert.rejects(a.run(join(root, "competing")), /already running/);
    const pid = Number(await waitFor(join(output, "pid")));
    await assert.rejects(b.run(output), /EEXIST/);
    await access(join(output, "pid"));
    const start = Date.now();
    controller.abort();
    await assert.rejects(a.run(join(root, "too-early")), /already running/);
    await a.shutdown();
    await rejected;
    assert.ok(Date.now() - start >= 700);
    await absent(output);
    try {
      process.kill(pid, 0);
      assert.match(await readFile(`/proc/${pid}/stat`, "utf8"), /\) Z /);
    } catch (error) {
      if (error.code !== "ESRCH" && error.code !== "ENOENT") throw error;
    }

    const early = new AbortController();
    await assert.rejects(a.run(join(root, "early"), early.signal, () => early.abort()), /abort/i);
    await absent(join(root, "early"));

    const success = join(root, "success");
    const result = await a.run(success, undefined, undefined, "@success.mp3");
    assert.equal(result.details.source, join(root, "@success.mp3"));
    assert.equal(result.details.artifacts.transcript, join(success, "é-transcript.md"));
    assert.equal(await readFile(result.details.artifacts.transcript, "utf8"), "private transcript");

    const shutdownOutput = join(root, "shutdown");
    const shutdownRun = a.run(shutdownOutput);
    const shutdownRejected = assert.rejects(shutdownRun, /abort/i);
    await waitFor(join(shutdownOutput, "pid"));
    await a.shutdown();
    await shutdownRejected;
    await absent(shutdownOutput);

    let started;
    const ready = new Promise(resolve => { started = resolve; });
    const command = a.command("hang.mp3", {
      hasUI: true,
      ui: { notify() {}, setStatus(_key, value) { if (value?.startsWith("processing")) started(); } },
    });
    await ready;
    await a.cancel();
    await command;
    const { readdir } = await import("node:fs/promises");
    assert.deepEqual(await readdir(process.env.PPS_OUTPUT_ROOT), []);
  } finally {
    process.env = saved;
    await rm(root, { recursive: true, force: true });
  }
});
