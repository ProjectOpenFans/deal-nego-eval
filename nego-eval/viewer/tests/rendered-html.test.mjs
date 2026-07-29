import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    {
      ASSETS: {
        fetch: async (request) => {
          const url = new URL(request.url);
          if (url.pathname === "/data/report.json") {
            return new Response(
              await readFile(new URL("../public/data/report.json", import.meta.url)),
              { headers: { "content-type": "application/json" } },
            );
          }
          return new Response("Not found", { status: 404 });
        },
      },
    },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("服务端渲染中文评测控制台", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /<title>谈判评测控制台<\/title>/i);
  assert.match(html, /正在加载完整证据链/);
  assert.doesNotMatch(html, /Your site is taking shape|react-loading-skeleton/i);
});

test("报告数据完整、可选择且不泄露密钥", async () => {
  const raw = await readFile(
    new URL("../public/data/report.json", import.meta.url),
    "utf8",
  );
  const report = JSON.parse(raw);
  assert.equal(report.summary.runs, report.runs.length);
  assert.equal(report.summary.cases, new Set(report.runs.map((run) => run.case_id)).size);
  assert.ok(report.runs.every((run) => run.episode.transcript.length > 0));
  assert.ok(report.runs.every((run) => !JSON.stringify(run).includes("api_key")));
  assert.doesNotMatch(JSON.stringify(report), /clean-deepseek|clean-test/i);
  assert.ok(report.runs.every((run) => run.case.input && run.case.meta && run.case.fixture));
});

test("Clean 与 On 对照组完整且使用同一模型路由", async () => {
  const raw = await readFile(
    new URL("../public/data/report.json", import.meta.url),
    "utf8",
  );
  const report = JSON.parse(raw);
  const clean = report.runs.filter((run) => run.arm === "clean");
  const on = report.runs.filter((run) => run.arm === "on");
  assert.equal(clean.length, 72);
  assert.equal(on.length, 72);
  assert.equal(report.summary.by_arm.clean.runs, 72);
  assert.equal(report.summary.by_arm.on.runs, 72);
  assert.ok(on.every((run) => run.episode.process.skills === "on"));
  assert.ok(on.every((run) => run.episode.process.skills_forced.includes("deal-diagnosis")));
  assert.ok(on.every((run) => run.episode.transcript.some((turn) => turn.speaker === "B")));
  assert.deepEqual(
    new Set(clean.map((run) => run.config.provenance.roles.buyer_negotiator.model)),
    new Set(on.map((run) => run.config.provenance.roles.buyer_negotiator.model)),
  );
});
