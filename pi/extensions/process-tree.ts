import { spawn, type ChildProcess } from "node:child_process";

export async function stopTree(child: ChildProcess): Promise<void> {
  if (!child.pid || child.exitCode !== null) return;
  if (process.platform === "win32") {
    await new Promise<void>((done) => {
      const killer = spawn("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"], {
        windowsHide: true,
        stdio: "ignore",
      });
      killer.once("exit", () => done());
      killer.once("error", () => done());
    });
  } else {
    try { process.kill(-child.pid, "SIGTERM"); } catch {}
    await new Promise((done) => setTimeout(done, 750));
    try { process.kill(-child.pid, "SIGKILL"); } catch {}
  }
}
