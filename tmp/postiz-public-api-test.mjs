import fs from 'node:fs/promises';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

const VIDEO_DIR = '/tmp/postiz-bulk-test';
const BASE_CANDIDATES = [
  'http://127.0.0.1:5000/api/public/v1',
  'http://127.0.0.1:3000/api/public/v1',
  'http://127.0.0.1:3000/public/v1',
];

const scheduleSlots = [
  '2026-06-02T07:00:00+07:00',
  '2026-06-02T08:00:00+07:00',
  '2026-06-02T09:00:00+07:00',
];

function titleFromFile(filePath) {
  return path.basename(filePath, path.extname(filePath));
}

function mb(bytes) {
  return Math.round((bytes / 1024 / 1024) * 10) / 10;
}

async function timed(label, fn) {
  const start = performance.now();
  const value = await fn();
  return { label, value, ms: Math.round(performance.now() - start) };
}

async function readJsonResponse(response) {
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text.slice(0, 500) };
  }
}

function pickMedia(json) {
  if (Array.isArray(json)) return json[0];
  if (Array.isArray(json?.files)) return json.files[0];
  if (Array.isArray(json?.media)) return json.media[0];
  if (json?.id) return json;
  return json?.data?.id ? json.data : null;
}

async function fetchJson(base, endpoint, apiKey, init = {}) {
  const response = await fetch(`${base}${endpoint}`, {
    ...init,
    headers: {
      Authorization: apiKey,
      ...(init.headers || {}),
    },
  });
  const json = await readJsonResponse(response);
  if (!response.ok) {
    const message = json?.message || json?.error || json?.raw || response.statusText;
    throw new Error(`${response.status} ${message}`);
  }
  return json;
}

async function findBase(apiKey) {
  const errors = [];
  for (const base of BASE_CANDIDATES) {
    try {
      await fetchJson(base, '/integrations', apiKey);
      return base;
    } catch (error) {
      errors.push(`${base}: ${error.message}`);
    }
  }
  throw new Error(`No Public API base worked: ${errors.join(' | ')}`);
}

async function getOrgAndIntegrations() {
  const org = await prisma.organization.findFirst({
    where: {
      apiKey: { not: null },
      Integration: {
        some: {
          deletedAt: null,
          disabled: false,
          refreshNeeded: false,
          providerIdentifier: { in: ['facebook', 'instagram'] },
        },
      },
    },
    select: {
      id: true,
      apiKey: true,
      Integration: {
        where: {
          deletedAt: null,
          disabled: false,
          refreshNeeded: false,
          providerIdentifier: { in: ['facebook', 'instagram'] },
        },
        select: {
          id: true,
          name: true,
          providerIdentifier: true,
        },
      },
    },
  });

  if (!org?.apiKey) throw new Error('Không tìm thấy organization có Public API key.');
  if (!org.Integration.length) throw new Error('Không tìm thấy kênh Facebook/Instagram đang hoạt động.');
  return org;
}

async function uploadMedia(base, apiKey, filePath) {
  const fileName = path.basename(filePath);
  const blob = await fs.openAsBlob(filePath, { type: 'video/mp4' });
  const form = new FormData();
  form.set('file', blob, fileName);

  const response = await fetch(`${base}/upload`, {
    method: 'POST',
    headers: { Authorization: apiKey },
    body: form,
  });
  const json = await readJsonResponse(response);
  if (!response.ok) {
    const message = json?.message || json?.error || json?.raw || response.statusText;
    throw new Error(`${response.status} ${message}`);
  }
  const media = pickMedia(json);
  if (!media?.id) {
    throw new Error(`Upload returned no media id. Keys: ${Object.keys(json || {}).join(',')}`);
  }
  return media;
}

async function scheduleMedia(base, apiKey, integrations, media, title, date, index) {
  const group = `bulk-api-test-${Date.now()}-${index}`;
  const imagePayload = {
    id: media.id,
    path: media.path,
    alt: media.alt || title,
    thumbnail: media.thumbnail,
  };
  const body = {
    type: 'schedule',
    shortLink: false,
    date,
    tags: [],
    posts: integrations.map((integration) => ({
      integration: { id: integration.id },
      group,
      value: [
        {
          id: '',
          content: title,
          delay: 0,
          image: [imagePayload],
        },
      ],
      settings: {
        post_type: 'post',
      },
    })),
  };

  const json = await fetchJson(base, '/posts', apiKey, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return { group, json };
}

async function deleteGroup(base, apiKey, group) {
  return fetchJson(base, `/posts/group/${encodeURIComponent(group)}`, apiKey, {
    method: 'DELETE',
  });
}

async function main() {
  const org = await getOrgAndIntegrations();
  const apiKey = org.apiKey;
  const integrations = org.Integration;
  const base = await findBase(apiKey);

  const files = (await fs.readdir(VIDEO_DIR))
    .filter((file) => /\.(mp4|mov|webm)$/i.test(file))
    .sort()
    .map((file) => path.join(VIDEO_DIR, file));

  if (files.length !== 3) {
    throw new Error(`Expected 3 test videos, found ${files.length}`);
  }

  console.log(`Public API base: ${base}`);
  console.log(
    `Channels: ${integrations
      .map((item) => `${item.providerIdentifier}:${item.name}`)
      .join(', ')}`
  );
  console.log(`Files: ${files.length}`);

  const results = [];
  for (const [index, filePath] of files.entries()) {
    const stat = await fs.stat(filePath);
    const title = titleFromFile(filePath);
    const row = {
      index: index + 1,
      title,
      sizeMb: mb(stat.size),
      uploadMs: null,
      scheduleMs: null,
      deleteMs: null,
      status: 'unknown',
      error: null,
    };

    let group = null;
    try {
      const upload = await timed('upload', () => uploadMedia(base, apiKey, filePath));
      row.uploadMs = upload.ms;
      const schedule = await timed('schedule', () =>
        scheduleMedia(base, apiKey, integrations, upload.value, title, scheduleSlots[index], index)
      );
      row.scheduleMs = schedule.ms;
      group = schedule.value.group;
      const cleanup = await timed('delete', () => deleteGroup(base, apiKey, group));
      row.deleteMs = cleanup.ms;
      row.status = 'ok';
    } catch (error) {
      row.status = 'failed';
      row.error = error.message;
      if (group) {
        try {
          const cleanup = await timed('delete-after-fail', () => deleteGroup(base, apiKey, group));
          row.deleteMs = cleanup.ms;
        } catch (cleanupError) {
          row.error += ` | cleanup failed: ${cleanupError.message}`;
        }
      }
    }
    results.push(row);
    console.log(JSON.stringify(row));
  }

  console.log('SUMMARY');
  console.table(
    results.map((row) => ({
      '#': row.index,
      sizeMb: row.sizeMb,
      uploadSec: row.uploadMs == null ? '-' : Math.round(row.uploadMs / 100) / 10,
      scheduleSec: row.scheduleMs == null ? '-' : Math.round(row.scheduleMs / 100) / 10,
      deleteSec: row.deleteMs == null ? '-' : Math.round(row.deleteMs / 100) / 10,
      status: row.status,
      title: row.title.slice(0, 42),
    }))
  );

  const failed = results.filter((row) => row.status !== 'ok');
  await prisma.$disconnect();
  if (failed.length) process.exitCode = 2;
}

main().catch(async (error) => {
  console.error(`FATAL: ${error.message}`);
  await prisma.$disconnect();
  process.exit(1);
});
