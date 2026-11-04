"use strict";

const messagesEl = document.getElementById("messages");
const timelineEl = document.getElementById("timeline");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send");
const roleSel = document.getElementById("role-select");
const statusBox = document.getElementById("conn-status");
const statusText = document.getElementById("conn-text");
const traceToggle = document.getElementById("trace-toggle");
const layoutEl = document.getElementById("layout");

let ws = null;
let roundNo = 0;
let round = null; // { roundEl, reasoningBody, answerEl }

/* ---------- 基础工具 ---------- */

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function now() {
  return new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

function scrollBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function scrollTimeline() {
  timelineEl.scrollTop = timelineEl.scrollHeight;
}

/* ---------- 连接状态 ---------- */

function setConn(ok, text) {
  statusBox.classList.toggle("ok", ok);
  statusText.textContent = text;
  sendBtn.disabled = !ok;
  inputEl.placeholder = ok
    ? "输入消息，Enter 发送，Shift+Enter 换行"
    : "正在连接服务，稍后自动重试…";
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  setConn(false, "连接中…");
  ws = new WebSocket(`${proto}://${location.host}/ws/chat`);
  ws.onopen = () => setConn(true, "已连接");
  ws.onclose = () => {
    setConn(false, "重连中…");
    setTimeout(connect, 2000);
  };
  ws.onmessage = (e) => handleMessage(JSON.parse(e.data));
}

function handleMessage(msg) {
  if (msg.type === "step") return renderStep(msg.step);
  if (msg.type === "done") return finishRound(msg.content);
  if (msg.type === "error") showError(msg.message);
}

/* ---------- 发送 ---------- */

function send() {
  const text = inputEl.value.trim();
  if (!text) return;
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    appendNotice("尚未连接到服务，正在自动重连，请稍候再发送。");
    return;
  }
  appendUser(text);
  startRound();
  ws.send(JSON.stringify({ message: text, role: roleSel.value }));
  inputEl.value = "";
  autosize();
}

/* ---------- 主区消息 ---------- */

function appendUser(text) {
  messagesEl.appendChild(el("div", "bubble user", text));
  scrollBottom();
}

function appendNotice(text) {
  const node = el("div", "bubble notice", text);
  messagesEl.appendChild(node);
  scrollBottom();
  setTimeout(() => node.remove(), 4000);
}

function showError(message) {
  messagesEl.appendChild(el("div", "bubble error", `出错了：${message}`));
  if (round) {
    const node = tlNode("error", "异常");
    nodeBody(node, message);
    round.roundEl.appendChild(node);
    scrollTimeline();
  }
  round = null;
  scrollBottom();
}

/* ---------- 时间线轮次 ---------- */

function startRound() {
  roundNo += 1;
  const empty = timelineEl.querySelector(".trace-empty");
  if (empty) empty.remove();

  const roundEl = el("div", "tl-round");
  roundEl.appendChild(el("div", "tl-round-title", `第 ${roundNo} 轮 · ${now()}`));
  timelineEl.appendChild(roundEl);

  round = { roundEl, reasoningBody: null, answerEl: null };
  scrollTimeline();
}

/* ---------- 时间线节点 ---------- */

function tlNode(cls, label) {
  const node = el("div", "tl-node " + cls);
  const head = el("div", "tl-head");
  head.appendChild(el("span", "tl-badge", label));
  head.appendChild(el("span", "tl-time", now()));
  node.appendChild(head);
  return node;
}

function nodeBody(node, text, mono) {
  const body = el("div", mono ? "tl-body mono" : "tl-body", text);
  node.appendChild(body);
  return body;
}

function renderStep(step) {
  if (!round) startRound();

  if (step.type === "reasoning") {
    if (!round.reasoningBody) {
      const node = tlNode("reasoning", "思考");
      round.reasoningBody = nodeBody(node, "");
      round.roundEl.appendChild(node);
    }
    round.reasoningBody.textContent += step.content;
    round.reasoningBody.scrollTop = round.reasoningBody.scrollHeight;
    scrollTimeline();
    return;
  }

  if (step.type === "tool_call") {
    const node = tlNode("toolcall", `调用 ${step.tool_name}`);
    nodeBody(node, JSON.stringify(step.tool_args), true);
    round.roundEl.appendChild(node);
    scrollTimeline();
    return;
  }

  if (step.type === "tool_result") {
    const node = tlNode("toolresult", `结果 · ${step.tool_name}`);
    const text = step.tool_result.length > 600
      ? step.tool_result.slice(0, 600) + " …"
      : step.tool_result;
    nodeBody(node, text, true);
    round.roundEl.appendChild(node);
    scrollTimeline();
    return;
  }

  if (step.type === "answer") {
    if (!round.answerEl) {
      round.answerEl = el("div", "bubble agent");
      messagesEl.appendChild(round.answerEl);
      const node = tlNode("answer", "回答");
      nodeBody(node, step.content.length > 400
        ? step.content.slice(0, 400) + " …" : step.content);
      round.roundEl.appendChild(node);
    }
    round.answerEl.textContent += step.content;
    scrollBottom();
    scrollTimeline();
  }
}

function finishRound(content) {
  if (round && !round.answerEl && content) {
    messagesEl.appendChild(el("div", "bubble agent", content));
  }
  round = null;
  scrollBottom();
}

/* ---------- 侧边栏开关 ---------- */

traceToggle.addEventListener("click", () => {
  layoutEl.classList.toggle("no-trace");
});

/* ---------- 初始化 ---------- */

function autosize() {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + "px";
}

fetch("/roles")
  .then((r) => r.json())
  .then((data) => {
    roleSel.innerHTML = "";
    const roles = (data.roles || []).slice().sort((a, b) => (a === "default" ? -1 : b === "default" ? 1 : a.localeCompare(b)));
    roles.forEach((r) => {
      const opt = document.createElement("option");
      opt.value = r;
      opt.textContent = r;
      roleSel.appendChild(opt);
    });
    if (roles.includes("default")) roleSel.value = "default";
  });

sendBtn.addEventListener("click", send);
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    send();
  }
});
inputEl.addEventListener("input", autosize);

connect();
