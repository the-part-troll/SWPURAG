"use strict";

const askForm = document.querySelector("#ask-form");
const questionInput = document.querySelector("#question");
const submitButton = document.querySelector("#ask-submit");
const statusBadge = document.querySelector("#result-status");
const resultContent = document.querySelector("#result-content");
const emptyState = document.querySelector("#empty-state");
const submittedQuestion = document.querySelector("#submitted-question");
const answerGroups = document.querySelector("#answer-groups");
const evidenceSection = document.querySelector("#evidence-section");
const evidenceCount = document.querySelector("#evidence-count");
const evidenceList = document.querySelector("#evidence-list");

const topics = new Map([
  ["admissions", "硕士招生"], ["library", "图书馆服务"], ["school_calendar", "校级放假与调休"],
]);
const statuses = new Map([
  ["answered", "已找到依据"], ["partial", "部分已回答"], ["clarify", "需要补充"],
  ["insufficient", "证据不足"], ["unavailable", "回答暂不可用"], ["error", "查询失败"],
  ["loading", "查询中"],
]);
const contexts = new Map([["table_header", "表头"], ["provision_heading", "条款标题"]]);
const readerGroups = new Map([["graduate", "研究生"], ["undergraduate", "本科生"], ["external", "校外读者"]]);
const noticeKinds = new Map([["regular", "常规安排"], ["temporary", "临时通知"], ["policy", "借阅规则"]]);

function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function statusFor(result) {
  if (result.status !== "answered" && result.claims?.length) return "partial";
  return statuses.has(result.status) ? result.status : "error";
}

function setStatus(node, status) {
  node.dataset.status = status;
  node.textContent = statuses.get(status);
  node.hidden = false;
}

function notice(status, message) {
  const box = element("div", "notice");
  box.dataset.status = status;
  const label = status === "clarify" ? "请补充信息" : statuses.get(status);
  box.append(element("strong", "", label), element("p", "", message));
  return box;
}

function evidenceId(value) {
  return Number.isSafeInteger(value) && value > 0 ? `evidence-${value}` : null;
}

function citationLink(citation) {
  const targetId = evidenceId(citation.id);
  const link = element("a", "citation", `[${citation.id}]`);
  link.href = `#${targetId}`;
  link.setAttribute("aria-label", `查看证据 ${citation.id}`);
  if (citation.quote) link.title = citation.quote;
  link.addEventListener("click", (event) => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    // 保留锚点跳转，同时让键盘焦点移到相应证据卡。
    document.getElementById(targetId)?.focus({ preventScroll: true });
  });
  return link;
}

function appendClaims(target, claims, availableIds) {
  if (!claims?.length) return;
  const list = element("ul", "claims");
  for (const claim of claims) {
    const item = element("li", "claim");
    const line = element("p", "", claim.text);
    const used = new Set();
    for (const citation of claim.citations || []) {
      if (!availableIds.has(citation.id) || used.has(citation.id)) continue;
      used.add(citation.id);
      line.append(" ", citationLink(citation));
    }
    item.append(line);
    list.append(item);
  }
  target.append(list);
}

function appendAnswerBody(target, result, availableIds) {
  if (result.scope_note) target.append(element("p", "scope-summary", result.scope_note));
  appendClaims(target, result.claims, availableIds);
  if (result.error || result.status === "unavailable") {
    target.append(notice("unavailable", result.error || "本次未能生成回答，可查看下方已找到的原文。"));
  } else if (result.follow_up) {
    const status = result.status === "clarify" ? "clarify" : "insufficient";
    target.append(notice(status, result.follow_up));
  } else if (!result.claims?.length) {
    target.append(notice("insufficient", "本次查询未找到可支持回答的原文。"));
  }
}

function scopeText(scope) {
  if (!scope || typeof scope !== "object") return "";
  const dateNote = scope.date_source === "assumed_year" ? "（年份按当前年）" : "";
  const schedule = scope.date ? `${scope.date}${dateNote}` : noticeKinds.get(scope.notice_kind);
  return [scope.campus, scope.building, schedule, readerGroups.get(scope.reader_group),
    scope.holidays?.join("、"),
    scope.study_modes?.join("、"), scope.colleges?.join("、"), scope.program_codes?.join("、"),
  ].filter(Boolean).join(" · ");
}

function answerTopic(topic, result, scope, availableIds) {
  const section = element("section", "answer-topic");
  const heading = element("header", "topic-heading");
  const badge = element("span", "status-badge");
  setStatus(badge, statusFor(result));
  heading.append(element("h3", "", topics.get(topic) || "回答"), badge);
  section.append(heading);
  const summary = scopeText(scope);
  if (summary) section.append(element("p", "scope-summary", summary));
  if (result.parts?.length) {
    for (const part of result.parts) {
      const partSection = element("section", "answer-subpart");
      partSection.append(element("h4", "", part.question));
      appendAnswerBody(partSection, part, availableIds);
      section.append(partSection);
    }
  } else {
    appendAnswerBody(section, result, availableIds);
  }
  return section;
}

function locatedLink(value, locator, local) {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const url = new URL(value, window.location.origin);
    // 本地原件仅用服务器返回的同源地址。官网链接仅允许 HTTP(S)。
    if (local && (!value.startsWith("/") || url.origin !== window.location.origin)) return null;
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return null;
    if (locator.kind === "pdf" && Number.isSafeInteger(locator.page) && locator.page > 0) {
      url.hash = `page=${locator.page}`;
    } else if (!url.hash && typeof locator.anchor === "string" && locator.anchor) {
      url.hash = encodeURIComponent(locator.anchor);
    }
    return url.href;
  } catch {
    return null;
  }
}

function outgoingLink(href, text, className) {
  const link = element("a", className, text);
  link.href = href;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.setAttribute("aria-label", `${text}（新标签页）`);
  return link;
}

function locationLabel(locator) {
  if (locator.kind === "pdf") {
    return [locator.page && `PDF 第 ${locator.page} 页`, locator.row && `表格第 ${locator.row} 行`].filter(Boolean).join(" · ");
  }
  return [locator.paragraph && `正文块 ${locator.paragraph}`,
    locator.line && `HTML 第 ${locator.line} 行${locator.column ? `第 ${locator.column} 列` : ""}`,
  ].filter(Boolean).join(" · ");
}

function applicability(item, locator) {
  if (item.evidence_topic === "library") {
    const range = { ...item, ...locator.library_scope };
    return [range.campus, range.building, noticeKinds.get(range.notice_kind), readerGroups.get(range.reader_group),
      range.effective_from && range.effective_to && `${range.effective_from} 至 ${range.effective_to}`,
    ].filter(Boolean).join(" · ");
  }
  if (item.evidence_topic === "school_calendar") {
    const range = locator.calendar_scope || {};
    return [range.holiday,
      range.effective_from && range.effective_to && `${range.effective_from} 至 ${range.effective_to}`,
      range.makeup_dates?.length && `调休上课 ${range.makeup_dates.join("、")}`,
    ].filter(Boolean).join(" · ");
  }
  return [item.admission_year && `${item.admission_year} 年招生`, locator.study_mode, item.audience].filter(Boolean).join(" · ");
}

function evidenceCard(item, quotes) {
  const locator = item.locator || {};
  const card = element("article", "evidence-card");
  card.id = evidenceId(item.id);
  card.tabIndex = -1;
  const heading = element("header", "evidence-card-heading");
  heading.append(element("span", "evidence-id", `[${item.id}]`), element("h5", "", item.title || "官网原文"));
  card.append(heading);

  const metadata = [item.unit, item.published_at && `发布于 ${item.published_at}`, locationLabel(locator), contexts.get(item.context)].filter(Boolean);
  if (metadata.length) card.append(element("p", "evidence-meta", metadata.join(" · ")));
  const appliesTo = applicability(item, locator);
  if (appliesTo) card.append(element("p", "evidence-meta", appliesTo));

  const original = item.text || "";
  const excerpt = quotes?.length ? quotes.join("\n…\n") : (item.snippet || original);
  card.append(element("blockquote", "evidence-excerpt", excerpt));
  if (original !== excerpt) {
    const details = element("details", "evidence-full");
    details.append(element("summary", "", "查看完整证据段"), element("p", "evidence-excerpt", original));
    card.append(details);
  }

  const links = element("div", "evidence-links");
  const officialUrl = locatedLink(item.url, locator, false);
  const archiveUrl = locatedLink(item.archive_url, locator, true);
  if (officialUrl) links.append(outgoingLink(officialUrl, "打开官网原文 ↗", "official-link"));
  if (archiveUrl) links.append(outgoingLink(archiveUrl, "查看本地原件 ↗", "archive-link"));
  if (links.childElementCount) card.append(links);
  return card;
}

function renderEvidence(items, claims) {
  if (!items.length) return;
  const quotes = new Map();
  for (const claim of claims || []) {
    for (const citation of claim.citations || []) {
      if (!citation.quote) continue;
      if (!quotes.has(citation.id)) quotes.set(citation.id, new Set());
      quotes.get(citation.id).add(citation.quote);
    }
  }
  const groups = new Map();
  for (const item of items) {
    const topic = item.evidence_topic;
    if (!groups.has(topic)) groups.set(topic, []);
    groups.get(topic).push(item);
  }
  for (const [topic, rows] of groups) {
    const group = element("section", "evidence-group");
    group.append(element("h4", "", topics.get(topic) || "来源"));
    for (const row of rows) group.append(evidenceCard(row, Array.from(quotes.get(row.id) || [])));
    evidenceList.append(group);
  }
  const rankedCount = items.filter((item) => Number.isSafeInteger(item.rank)).length;
  const contextCount = items.filter((item) => item.context).length;
  evidenceCount.textContent = rankedCount || contextCount
    ? [`${rankedCount} 条检索结果`, contextCount && `${contextCount} 条引用上下文`].filter(Boolean).join(" · ")
    : `${items.length} 条证据`;
  evidenceSection.hidden = false;
}

function renderResult(result) {
  const items = Array.isArray(result.evidence) ? result.evidence.filter((item) => evidenceId(item.id)) : [];
  const availableIds = new Set(items.map((item) => item.id));
  setStatus(statusBadge, statusFor(result));
  const sections = result.topic_answers
    ? Object.entries(result.topic_answers)
    : [[result.topics?.[0], result]];
  for (const [topic, answer] of sections) {
    const scope = result.topic_answers ? result.scope?.[topic] : result.scope;
    answerGroups.append(answerTopic(topic, answer, scope, availableIds));
  }
  renderEvidence(items, result.claims);
}

function clearResult(question) {
  emptyState.hidden = true;
  submittedQuestion.textContent = question;
  submittedQuestion.hidden = false;
  answerGroups.replaceChildren();
  evidenceList.replaceChildren();
  evidenceSection.hidden = true;
  if (window.location.hash.startsWith("#evidence-")) {
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  }
}

document.querySelectorAll(".example-button").forEach((button) => {
  button.addEventListener("click", () => {
    questionInput.value = button.dataset.question;
    questionInput.setCustomValidity("");
    questionInput.focus();
  });
});

questionInput.addEventListener("input", () => questionInput.setCustomValidity(""));
questionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !event.isComposing) {
    event.preventDefault();
    if (!submitButton.disabled) askForm.requestSubmit();
  }
});

askForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (submitButton.disabled) return;
  const question = questionInput.value.trim();
  if (!question) {
    questionInput.setCustomValidity("请输入问题。");
    questionInput.reportValidity();
    return;
  }

  clearResult(question);
  setStatus(statusBadge, "loading");
  answerGroups.append(element("p", "empty-state loading-message", "正在检索原文并整理回答…"));
  submitButton.disabled = true;
  resultContent.setAttribute("aria-busy", "true");
  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ question }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "本地服务未能处理本次查询。");
    if (!result || !statuses.has(result.status)) throw new Error("本地服务返回了无法显示的结果。");
    answerGroups.replaceChildren();
    renderResult(result);
  } catch (error) {
    setStatus(statusBadge, "error");
    answerGroups.replaceChildren(notice("error", error instanceof TypeError
      ? "无法连接本地问答服务，请确认服务正在运行后重试。"
      : error instanceof SyntaxError ? "本地服务返回了无法显示的结果。" : error.message));
  } finally {
    submitButton.disabled = false;
    resultContent.setAttribute("aria-busy", "false");
  }
});
