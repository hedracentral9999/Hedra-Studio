#!/usr/bin/env tsx
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";

loadEnvFile(".env.local");

function loadEnvFile(path: string): void {
  if (!existsSync(path)) return;
  const lines = readFileSync(path, "utf8").split(/\r?\n/);
  for (const raw of lines) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const [key, ...rest] = line.split("=");
    if (!key || process.env[key]) continue;
    process.env[key] = rest.join("=").trim().replace(/^['"]|['"]$/g, "");
  }
}

interface Article {
  url: string;
  domain: string;
  title: string;
  text: string;
  image: string | null;
}

interface Args {
  url?: string;
  outDir?: string;
}

function parseArgs(argv: string[]): Args {
  const args: Args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];
    if (arg === "--url" && next) {
      args.url = next;
      i += 1;
    } else if (arg === "--out-dir" && next) {
      args.outDir = next;
      i += 1;
    }
  }
  return args;
}

function decodeEntities(text: string): string {
  return text
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&aacute;/g, "á")
    .replace(/&agrave;/g, "à")
    .replace(/&atilde;/g, "ã")
    .replace(/&acirc;/g, "â")
    .replace(/&eacute;/g, "é")
    .replace(/&egrave;/g, "è")
    .replace(/&ecirc;/g, "ê")
    .replace(/&iacute;/g, "í")
    .replace(/&ograve;/g, "ò")
    .replace(/&oacute;/g, "ó")
    .replace(/&ocirc;/g, "ô")
    .replace(/&uacute;/g, "ú")
    .replace(/&ugrave;/g, "ù")
    .replace(/&yacute;/g, "ý")
    .replace(/&Aacute;/g, "Á")
    .replace(/&Eacute;/g, "É")
    .replace(/&Ocirc;/g, "Ô")
    .replace(/&Uacute;/g, "Ú")
    .replace(/&Đ;/g, "Đ");
}

function htmlText(html: string): string {
  return decodeEntities(html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim());
}

function metaContent(html: string, property: string): string {
  const re = new RegExp(`<meta[^>]+(?:property|name)=["']${property}["'][^>]+content=["']([^"']+)["'][^>]*>`, "i");
  const re2 = new RegExp(`<meta[^>]+content=["']([^"']+)["'][^>]+(?:property|name)=["']${property}["'][^>]*>`, "i");
  return decodeEntities((html.match(re)?.[1] || html.match(re2)?.[1] || "").trim());
}

function titleFromHtml(html: string): string {
  return metaContent(html, "og:title")
    || decodeEntities(html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1]?.trim() || "");
}

function slugify(text: string): string {
  return text.normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .replace(/[^a-zA-Z0-9\s-]/g, "")
    .trim()
    .toLowerCase()
    .replace(/[\s_-]+/g, "-")
    .slice(0, 64) || "finance-video";
}

async function fetchText(url: string): Promise<string> {
  const res = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml",
    },
  });
  if (!res.ok) throw new Error(`${url} -> HTTP ${res.status}`);
  return res.text();
}

function extractArticle(html: string, url: string): Article {
  const domain = new URL(url).hostname.replace(/^www\./, "");
  const title = titleFromHtml(html).replace(/\s*[-|]\s*ThuanCapital\s*$/i, "").trim();
  const image = metaContent(html, "og:image") || null;
  const articleHtml = html.match(/<article[\s\S]*?<\/article>/i)?.[0]
    || html.match(/<main[\s\S]*?<\/main>/i)?.[0]
    || html;
  const text = htmlText(articleHtml)
    .replace(/MENU Login Trang Chủ[\s\S]*?Bạn đang tìm kiếm điều gì\?/i, "")
    .replace(/THUANCAPITAL\s*⚠️[\s\S]*$/i, "")
    .replace(/► Tham gia[\s\S]*$/i, "")
    .replace(/\s+/g, " ")
    .trim();
  return { url, domain, title, text: text.slice(0, 6500), image };
}

function parseJson(raw: string): unknown {
  let text = raw.trim();
  if (text.startsWith("```")) {
    text = text.replace(/^```(?:json)?/i, "").replace(/```$/i, "").trim();
  }
  const first = text.indexOf("{");
  const last = text.lastIndexOf("}");
  if (first >= 0 && last > first) text = text.slice(first, last + 1);
  return JSON.parse(text);
}

function systemPrompt(article: Article): string {
  const channel = process.env.TIKTOK_DISPLAY_NAME || "Hedra Central";
  return `Bạn là AI biên tập video tài chính tiếng Việt cho kênh ${channel}.

Nhiệm vụ: biến bài báo thành script ngắn dùng cho Escbase finance template.

Quy tắc:
- Chỉ JSON thuần, không markdown.
- Đúng 6 scenes, mỗi scene 1 voiceText tiếng Việt tự nhiên.
- Tổng voiceText khoảng 170-210 từ.
- Số câu phải khớp template Escbase:
  scene 1 đúng 1 câu.
  scene 2 đúng 3 câu.
  scene 3 đúng 3 câu.
  scene 4 đúng 3 câu.
  scene 5 đúng 4 câu.
  scene 6 đúng 3 câu.
- Mỗi câu 7-13 từ, kết thúc bằng dấu ".", "?" hoặc "!".
- Không dùng dấu chấm phẩy để giả làm nhiều câu.
- Text visual phải viết ngắn để vừa slot, không trông như demo:
  headline <= 34 ký tự, subhead <= 58 ký tự, mỗi chip <= 12 ký tự.
  title <= 24 ký tự, highlight <= 22 ký tự.
  metric/callout/left/right/bullet/risk/focus/verdict đều phải ngắn, ưu tiên số liệu chính.
- Mapping voice/visual bắt buộc:
  scene 2: câu 1 khớp title/highlight, câu 2 khớp metric1, câu 3 khớp metric2 hoặc metric3.
  scene 3: câu 1 khớp title, câu 2 khớp highlight, câu 3 khớp callout.
  scene 4: câu 1 khớp left, câu 2 khớp bullet1, câu 3 khớp bullet2.
  scene 5: câu 1 mở risk tổng quan, câu 2 khớp risk1, câu 3 khớp risk2, câu 4 khớp risk3.
  scene 6: câu 1 khớp focus, câu 2 khớp verdict, câu 3 là câu theo dõi/nhận định chốt.
- Không đưa ý mới vào voiceText nếu slide đó không có visual field tương ứng.
- Viết cô đọng như bản tin tài chính TikTok, không giải thích lan man.
- Nội dung bám bài, không bịa số liệu.
- Ưu tiên thị trường, BTC, crypto, cổ phiếu, AI, ETF, Fed, dầu, địa chính trị nếu có.
- Không dùng "Xin chào" hoặc "Hôm nay chúng ta".
- voice.provider luôn là "elevenlabs".
- voice.voiceId luôn là "${process.env.ELEVENLABS_VOICE_ID || "6adFm46eyy74snVn6YrT"}".

Output schema:
{
  "version": "1.0",
  "metadata": {
    "title": "tên ngắn",
    "source": {"url": "${article.url}", "domain": "${article.domain}", "image": ${JSON.stringify(article.image)}},
    "channel": "${channel}",
    "theme": "finance-gold"
  },
  "voice": {"provider": "elevenlabs", "voiceId": "${process.env.ELEVENLABS_VOICE_ID || "6adFm46eyy74snVn6YrT"}", "speed": 1.0},
  "scenes": [
    {"id":"hook","type":"hook","voiceText":"...","visual":{"headline":"...", "subhead":"...", "chips":["...", "...", "...", "..."]}},
    {"id":"body-1","type":"body","voiceText":"...","visual":{"title":"...", "highlight":"...", "metric1":"...", "metric2":"...", "metric3":"..."}},
    {"id":"body-2","type":"body","voiceText":"...","visual":{"title":"...", "highlight":"...", "callout":"..."}},
    {"id":"body-3","type":"body","voiceText":"...","visual":{"title":"...", "left":"...", "right":"...", "bullet1":"...", "bullet2":"..."}},
    {"id":"body-4","type":"body","voiceText":"...","visual":{"title":"...", "risk1":"...", "risk2":"...", "risk3":"..."}},
    {"id":"outro","type":"outro","voiceText":"...","visual":{"title":"KỊCH BẢN THEO DÕI", "focus":"...", "verdict":"..."}}
  ]
}`;
}

async function generateScript(article: Article): Promise<any> {
  const apiKey = process.env.CLAUDE_API_KEY;
  if (!apiKey) throw new Error("Missing CLAUDE_API_KEY in Auto-Create-Video/.env.local");
  const model = process.env.CLAUDE_MODEL || "claude-sonnet-4-6";
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model,
      max_tokens: 2400,
      system: systemPrompt(article),
      messages: [{ role: "user", content: `Tiêu đề: ${article.title}\n\nNội dung bài:\n${article.text.slice(0, 5200)}\n\nTạo script JSON.` }],
    }),
  });
  if (!res.ok) throw new Error(`Claude ${res.status}: ${(await res.text()).slice(0, 500)}`);
  const data = await res.json() as any;
  const text = data.content?.find((p: any) => p.type === "text")?.text || data.content?.[0]?.text || "";
  const script = parseJson(text);
  if (!script || typeof script !== "object" || !Array.isArray((script as any).scenes)) {
    throw new Error("Claude response did not contain script scenes");
  }
  return script;
}

function normalizeScript(script: any, article: Article): any {
  const voiceId = process.env.ELEVENLABS_VOICE_ID || "6adFm46eyy74snVn6YrT";
  const requiredSentenceCounts = [1, 3, 3, 3, 4, 3];
  script.version = "1.0";
  script.metadata ||= {};
  script.metadata.title ||= article.title;
  script.metadata.source = { url: article.url, domain: article.domain, image: article.image };
  script.metadata.channel ||= process.env.TIKTOK_DISPLAY_NAME || "Hedra Central";
  script.metadata.theme ||= "finance-gold";
  script.voice = { provider: "elevenlabs", voiceId, speed: 1.0 };
  script.scenes = script.scenes.slice(0, 6).map((scene: any, idx: number) => {
    const voiceText = normalizeVoiceText(String(scene.voiceText || ""));
    requireSentenceCount(voiceText, requiredSentenceCounts[idx], idx);
    const sentences = splitSentences(voiceText);
    return {
      ...scene,
      id: idx === 0 ? "hook" : idx === 5 ? "outro" : `body-${idx}`,
      type: idx === 0 ? "hook" : idx === 5 ? "outro" : "body",
      voiceText,
      visual: normalizeVisual(scene.visual || {}, idx, sentences),
    };
  });
  if (script.scenes.length !== 6 || script.scenes.some((s: any) => !s.voiceText)) {
    throw new Error("Script must contain exactly 6 scenes with voiceText");
  }
  return script;
}

function fit(text: unknown, limit: number): string {
  const value = String(text || "").replace(/\s+/g, " ").trim();
  if (value.length <= limit) return value;
  const cut = value.slice(0, limit).replace(/\s+\S*$/, "").trim();
  return cut || value.slice(0, limit).trim();
}

function visualFromSentence(sentence: string, limit: number): string {
  return fit(sentence.replace(/[.!?]+$/g, ""), limit);
}

function normalizeVisual(visual: any, idx: number, sentences: string[]): any {
  if (idx === 0) {
    const chips = Array.isArray(visual.chips) ? visual.chips : [];
    return {
      headline: fit(visual.headline, 34),
      subhead: fit(visual.subhead, 58),
      chips: chips.slice(0, 4).map((item: unknown) => fit(item, 12)),
    };
  }
  if (idx === 1) {
    return {
      title: fit(visual.title, 24),
      highlight: fit(visual.highlight, 22),
      metric1: visualFromSentence(sentences[1] || visual.metric1, 26),
      metric2: visualFromSentence(sentences[2] || visual.metric2, 26),
      metric3: fit(visual.metric3, 26),
    };
  }
  if (idx === 2) {
    return {
      title: fit(visual.title, 24),
      highlight: visualFromSentence(sentences[1] || visual.highlight, 26),
      callout: visualFromSentence(sentences[2] || visual.callout, 54),
    };
  }
  if (idx === 3) {
    return {
      title: fit(visual.title, 24),
      left: visualFromSentence(sentences[0] || visual.left, 18),
      right: fit(visual.right || sentences[1], 18),
      bullet1: visualFromSentence(sentences[1] || visual.bullet1, 28),
      bullet2: visualFromSentence(sentences[2] || visual.bullet2, 28),
    };
  }
  if (idx === 4) {
    return {
      title: fit(visual.title, 24),
      risk1: visualFromSentence(sentences[1] || visual.risk1, 36),
      risk2: visualFromSentence(sentences[2] || visual.risk2, 36),
      risk3: visualFromSentence(sentences[3] || visual.risk3, 36),
    };
  }
  return {
    title: fit(visual.title || "KỊCH BẢN THEO DÕI", 24),
    focus: visualFromSentence(sentences[0] || visual.focus, 30),
    verdict: visualFromSentence(sentences[1] || visual.verdict, 76),
  };
}

function normalizeVoiceText(text: string): string {
  const cleaned = text
    .replace(/\s+/g, " ")
    .replace(/[;；]+/g, ".")
    .trim();
  return /[.!?]$/.test(cleaned) ? cleaned : `${cleaned}.`;
}

function splitSentences(text: string): string[] {
  const protectedText = text.replace(/(\d)\.(\d)/g, "$1<DECIMAL>$2");
  return protectedText
    .match(/[^.!?]+[.!?]+/g)
    ?.map((item) => item.replace(/<DECIMAL>/g, ".").trim())
    .filter(Boolean) || [];
}

function requireSentenceCount(text: string, expected: number, idx: number): void {
  const actual = splitSentences(text).length;
  if (actual !== expected) {
    throw new Error(`Scene ${idx + 1} must have exactly ${expected} sentences, got ${actual}: ${text}`);
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.url) throw new Error("Usage: tsx scripts/article-to-script.ts --url URL [--out-dir DIR]");
  const html = await fetchText(args.url);
  const article = extractArticle(html, args.url);
  const fallbackDir = resolve("output", `${slugify(article.title)}-${new Date().toISOString().slice(0, 10).replace(/-/g, "")}`);
  const outDir = resolve(args.outDir || fallbackDir);
  mkdirSync(outDir, { recursive: true });
  const script = normalizeScript(await generateScript(article), article);
  const scriptPath = join(outDir, "script.json");
  const textPath = join(outDir, "script-90s.txt");
  const articlePath = join(outDir, "article.json");
  writeFileSync(scriptPath, JSON.stringify(script, null, 2), "utf8");
  writeFileSync(textPath, script.scenes.map((s: any) => s.voiceText).join("\n"), "utf8");
  writeFileSync(articlePath, JSON.stringify(article, null, 2), "utf8");
  if (!existsSync(dirname(scriptPath))) mkdirSync(dirname(scriptPath), { recursive: true });
  console.log(`title=${article.title}`);
  console.log(`slug=${basename(outDir)}`);
  console.log(`script=${scriptPath}`);
  console.log(`scriptText=${textPath}`);
  console.log(`article=${articlePath}`);
}

main().catch((err) => {
  console.error(err instanceof Error ? err.message : err);
  process.exit(1);
});
