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

test("失败分析覆盖全部运行，并明确 simulator 参与", async () => {
  const raw = await readFile(
    new URL("../public/data/failure-analysis.json", import.meta.url),
    "utf8",
  );
  const failure = JSON.parse(raw);
  assert.equal(
    failure.failure_groups.reduce((sum, group) => sum + group.count, 0),
    failure.runs,
  );
  assert.equal(failure.passed + failure.failed, failure.runs);
  assert.equal(failure.simulator.runs_with_counterparty, failure.runs);
  assert.equal(failure.simulator.model, "Qwen3.6-27B-NVFP4");
  assert.ok(failure.simulator.counterparty_turns > failure.runs);
  assert.ok(failure.quality.high_quality_failures > 0);
});
