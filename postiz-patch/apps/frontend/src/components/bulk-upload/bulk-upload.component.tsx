'use client';

import React, {
  ChangeEvent,
  DragEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { useFetch } from '@gitroom/helpers/utils/custom.fetch';

type Integration = {
  id: string;
  name: string;
  identifier?: string;
  providerIdentifier?: string;
  type?: string;
  picture?: string;
  disabled?: boolean;
  refreshNeeded?: boolean;
};

type DriveFile = {
  id: string;
  name: string;
  title: string;
  size?: number | null;
};

type DriveStatus = {
  configured: boolean;
  connected: boolean;
  folderConfigured: boolean;
  folderUrl: string;
  redirectUri: string;
  readiness?: {
    oauthClient: boolean;
    driveToken: boolean;
    driveFolder: boolean;
    so9DriveReady: boolean;
  };
};

type RowStatus = 'queued' | 'uploading' | 'scheduled' | 'error';

type UploadRow = {
  id: string;
  source: 'local' | 'drive';
  file?: File;
  driveFileId?: string;
  fileName: string;
  title: string;
  size?: number | null;
  scheduledAt: string;
  status: RowStatus;
  progress: number;
  error?: string;
};

const DEFAULT_DRIVE_FOLDER =
  'https://drive.google.com/drive/folders/15xam_1626LScLFl_aEsuPMb8XT0GYtAs';

function titleFromName(name: string) {
  return name.replace(/\.[^/.]+$/, '').trim();
}

function pad(value: number) {
  return String(value).padStart(2, '0');
}

function toInputDate(date: Date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate()
  )}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function fromInputDate(value: string) {
  const date = new Date(value);
  return date.toISOString();
}

function addMinutes(value: string, minutes: number) {
  const date = new Date(value);
  date.setMinutes(date.getMinutes() + minutes);
  return toInputDate(date);
}

function formatBytes(value?: number | null) {
  if (!value) {
    return '-';
  }

  const units = ['B', 'KB', 'MB', 'GB'];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }

  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

const statusText: Record<RowStatus, string> = {
  queued: 'Chờ xử lý',
  uploading: 'Đang tải',
  scheduled: 'Đã lên lịch',
  error: 'Lỗi',
};

function integrationProvider(integration: Integration) {
  const source = [
    integration.identifier,
    integration.providerIdentifier,
    integration.type,
    integration.name,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  if (source.includes('instagram')) {
    return 'Instagram';
  }

  if (source.includes('facebook')) {
    return 'Facebook';
  }

  return 'Kênh';
}

function isPublishIntegration(integration: Integration) {
  const provider = integrationProvider(integration);
  return provider === 'Facebook' || provider === 'Instagram';
}

function shortProvider(integration: Integration) {
  return integrationProvider(integration) === 'Instagram' ? 'IG' : 'FB';
}

export function BulkUploadComponent() {
  const fetch = useFetch();
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [selectedIntegrationIds, setSelectedIntegrationIds] = useState<string[]>(
    []
  );
  const [rows, setRows] = useState<UploadRow[]>([]);
  const [mode, setMode] = useState<'local' | 'drive'>('local');
  const [startAt, setStartAt] = useState(() => {
    const date = new Date();
    date.setDate(date.getDate() + 1);
    date.setHours(7, 0, 0, 0);
    return toInputDate(date);
  });
  const [intervalMinutes, setIntervalMinutes] = useState(60);
  const [driveFolder, setDriveFolder] = useState(DEFAULT_DRIVE_FOLDER);
  const [driveConnected, setDriveConnected] = useState(false);
  const [driveConfigured, setDriveConfigured] = useState(false);
  const [driveFolderConfigured, setDriveFolderConfigured] = useState(false);
  const [driveRedirectUri, setDriveRedirectUri] = useState('');
  const [driveClientId, setDriveClientId] = useState('');
  const [driveClientSecret, setDriveClientSecret] = useState('');
  const [driveScanned, setDriveScanned] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const loadIntegrations = useCallback(async () => {
    try {
      const response = await fetch('/bulk-upload/integrations');
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const data = await response.json();
      const list = Array.isArray(data) ? data : data?.integrations || [];
      const filtered = list.filter((integration: Integration) => {
        return (
          !integration.disabled &&
          !integration.refreshNeeded &&
          isPublishIntegration(integration)
        );
      });

      setIntegrations(filtered);
      setSelectedIntegrationIds(
        filtered.map((integration: Integration) => integration.id)
      );
      setMessage(
        filtered.length
          ? `Đã tải ${filtered.length} kênh đăng.`
          : 'Chưa thấy kênh Facebook/Instagram đang hoạt động. Vào Tích hợp để kiểm tra kết nối.'
      );
    } catch (error) {
      setMessage('Không tải được danh sách kênh. Bấm Tải lại hoặc kiểm tra Tích hợp.');
    }
  }, [fetch]);

  const selectedIntegrations = useMemo(
    () =>
      integrations.filter((integration) =>
        selectedIntegrationIds.includes(integration.id)
      ),
    [integrations, selectedIntegrationIds]
  );

  const processedCount = useMemo(
    () => rows.filter((row) => row.status === 'scheduled').length,
    [rows]
  );

  const pendingCount = rows.length - processedCount;
  const driveReadiness = useMemo(
    () => [
      { label: 'OAuth', ok: driveConfigured },
      { label: 'Token', ok: driveConnected },
      { label: 'Folder', ok: driveFolderConfigured },
      { label: 'Scan', ok: driveScanned },
    ],
    [driveConfigured, driveConnected, driveFolderConfigured, driveScanned]
  );

  const refreshDriveStatus = useCallback(async () => {
    try {
      const response = await fetch('/bulk-upload/drive/status');
      const data = (await response.json()) as DriveStatus;
      setDriveConfigured(!!data.configured);
      setDriveConnected(!!data.connected);
      setDriveFolderConfigured(!!data.folderConfigured);
      setDriveRedirectUri(data.redirectUri || '');
      if (data.folderUrl) {
        setDriveFolder(data.folderUrl);
      }
    } catch (error) {
      setDriveConfigured(false);
      setDriveConnected(false);
      setDriveFolderConfigured(false);
    }
  }, [fetch]);

  useEffect(() => {
    loadIntegrations();
    refreshDriveStatus();
  }, [loadIntegrations, refreshDriveStatus]);

  const buildRowsFromFiles = useCallback(
    (files: File[]) => {
      const videos = files
        .filter((file) => /\.(mp4|mov|webm)$/i.test(file.name))
        .slice(0, 50);

      const newRows = videos.map((file, index) => ({
        id: `${file.name}-${file.size}-${file.lastModified}`,
        source: 'local' as const,
        file,
        fileName: file.name,
        title: titleFromName(file.name),
        size: file.size,
        scheduledAt: addMinutes(startAt, index * intervalMinutes),
        status: 'queued' as const,
        progress: 0,
      }));

      setRows(newRows);
      setMessage(
        newRows.length
          ? `Đã nhận ${newRows.length} video. Tiêu đề lấy đúng từ tên file.`
          : 'Không thấy video hợp lệ. Chỉ nhận .mp4, .mov, .webm.'
      );
    },
    [intervalMinutes, startAt]
  );

  const handleFileInput = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      buildRowsFromFiles(Array.from(event.target.files || []));
      event.target.value = '';
    },
    [buildRowsFromFiles]
  );

  const handleDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      buildRowsFromFiles(Array.from(event.dataTransfer.files || []));
    },
    [buildRowsFromFiles]
  );

  const scanDrive = useCallback(async () => {
    setLoading(true);
    setMessage('');
    try {
      const response = await fetch('/bulk-upload/drive/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folderUrl: driveFolder }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.message || 'Không quét được Google Drive');
      }

      const driveRows = (data.files || [])
        .slice(0, 200)
        .map((file: DriveFile, index: number) => ({
          id: file.id,
          source: 'drive' as const,
          driveFileId: file.id,
          fileName: file.name,
          title: file.title || titleFromName(file.name),
          size: file.size,
          scheduledAt: addMinutes(startAt, index * intervalMinutes),
          status: 'queued' as const,
          progress: 0,
        }));

      setRows(driveRows);
      setDriveScanned(true);
      setMessage(`Đã quét ${driveRows.length} video từ Google Drive.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không quét được Drive');
    } finally {
      setLoading(false);
    }
  }, [driveFolder, fetch, intervalMinutes, startAt]);

  const saveDriveConfig = useCallback(async () => {
    setLoading(true);
    setMessage('');
    try {
      const response = await fetch('/bulk-upload/drive/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          clientId: driveClientId,
          clientSecret: driveClientSecret,
          redirectUri: driveRedirectUri,
          folderUrl: driveFolder,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.message || 'Không lưu được Google OAuth');
      }
      setDriveClientSecret('');
      setMessage('Đã lưu Google OAuth trong Postiz. Bấm Kết nối Drive để cấp quyền.');
      await refreshDriveStatus();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không lưu được Google OAuth');
    } finally {
      setLoading(false);
    }
  }, [
    driveClientId,
    driveClientSecret,
    driveFolder,
    driveRedirectUri,
    fetch,
    refreshDriveStatus,
  ]);

  const saveDriveFolder = useCallback(async () => {
    setLoading(true);
    setMessage('');
    try {
      const response = await fetch('/bulk-upload/drive/folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folderUrl: driveFolder }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.message || 'Không lưu được folder Drive');
      }
      setMessage('Đã lưu folder Drive trong Postiz.');
      await refreshDriveStatus();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Không lưu được folder Drive');
    } finally {
      setLoading(false);
    }
  }, [driveFolder, fetch, refreshDriveStatus]);

  const connectDrive = useCallback(async () => {
    try {
      const response = await fetch('/bulk-upload/drive/auth-url');
      const data = await response.json();
      if (data.url) {
        window.location.href = data.url;
      }
    } catch (error) {
      setMessage('Google Drive OAuth chưa được cấu hình trong Postiz.');
    }
  }, [fetch]);

  const updateRow = useCallback((id: string, patch: Partial<UploadRow>) => {
    setRows((current) =>
      current.map((row) => (row.id === id ? { ...row, ...patch } : row))
    );
  }, []);

  const runBatch = useCallback(
    async (onlyRowId?: string) => {
      if (!selectedIntegrationIds.length) {
        setMessage('Chọn ít nhất một kênh Facebook hoặc Instagram trước.');
        return;
      }

      setLoading(true);
      setMessage('');
      const runnable = rows.filter((row) =>
        onlyRowId ? row.id === onlyRowId : row.status === 'queued' || row.status === 'error'
      );

      for (const row of runnable) {
        updateRow(row.id, { status: 'uploading', progress: 10, error: undefined });
        try {
          if (row.source === 'local') {
            if (!row.file) {
              throw new Error('Thiếu file local');
            }

            const formData = new FormData();
            formData.append('file', row.file);
            const uploadResponse = await fetch('/bulk-upload/upload', {
              method: 'POST',
              body: formData,
            });
            const media = await uploadResponse.json();
            if (!uploadResponse.ok) {
              throw new Error(media?.message || 'Upload lỗi');
            }

            updateRow(row.id, { progress: 70 });
            const scheduleResponse = await fetch('/bulk-upload/schedule', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                mediaId: media.id,
                title: row.title,
                integrationIds: selectedIntegrationIds,
                scheduledAt: fromInputDate(row.scheduledAt),
              }),
            });
            const schedule = await scheduleResponse.json();
            if (!scheduleResponse.ok) {
              throw new Error(schedule?.message || 'Lên lịch lỗi');
            }
          } else {
            const response = await fetch('/bulk-upload/drive/import', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                fileId: row.driveFileId,
                fileName: row.fileName,
                title: row.title,
                integrationIds: selectedIntegrationIds,
                scheduledAt: fromInputDate(row.scheduledAt),
              }),
            });
            const data = await response.json();
            if (!response.ok) {
              throw new Error(data?.message || 'Import Drive lỗi');
            }
          }

          updateRow(row.id, { status: 'scheduled', progress: 100 });
        } catch (error) {
          updateRow(row.id, {
            status: 'error',
            progress: 0,
            error: error instanceof Error ? error.message : 'Có lỗi không xác định',
          });
        }
      }

      setLoading(false);
    },
    [fetch, rows, selectedIntegrationIds, updateRow]
  );

  const mainAction = useMemo(() => {
    if (loading) {
      return `Đang xử lý ${processedCount}/${rows.length || 0}`;
    }
    if (mode === 'drive' && !rows.length) {
      return 'Quét Drive';
    }
    if (!rows.length) {
      return 'Chọn video';
    }
    if (!selectedIntegrationIds.length) {
      return 'Chọn kênh đăng';
    }
    return 'Tự tải & lên lịch';
  }, [loading, mode, processedCount, rows.length, selectedIntegrationIds.length]);

  const handleMainAction = useCallback(() => {
    if (loading) {
      return;
    }
    if (mode === 'drive' && !rows.length) {
      scanDrive();
      return;
    }
    if (rows.length) {
      runBatch();
    }
  }, [loading, mode, rows.length, runBatch, scanDrive]);

  return (
    <div className="min-h-full bg-[#f7f7f8] px-[32px] py-[28px] text-[#111113]">
      <div className="mx-auto flex max-w-[1380px] flex-col gap-[18px]">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[28px] font-semibold tracking-[-0.01em]">
              Tải video hàng loạt
            </div>
            <div className="mt-[4px] text-[14px] text-[#6f7177]">
              Upload nhiều video vào Postiz, lấy tên file làm tiêu đề và tự xếp lịch.
            </div>
          </div>
          <button
            onClick={handleMainAction}
            disabled={
              loading ||
              (!rows.length && mode === 'local') ||
              (!!rows.length && !selectedIntegrationIds.length)
            }
            className="rounded-[10px] bg-[#111113] px-[18px] py-[12px] text-[14px] font-semibold text-white disabled:cursor-not-allowed disabled:bg-[#c9c9ce]"
          >
            {mainAction}
          </button>
        </div>

        <div className="grid grid-cols-[320px_1fr] gap-[18px]">
          <aside className="flex flex-col gap-[14px] rounded-[14px] border border-[#e7e7ea] bg-white p-[18px]">
            <div>
              <div className="flex items-center justify-between">
                <div className="text-[13px] font-semibold text-[#6f7177]">
                  Kênh đăng
                </div>
                <button
                  onClick={loadIntegrations}
                  className="rounded-[8px] border border-[#dedee3] px-[9px] py-[6px] text-[12px] font-semibold text-[#33343a]"
                >
                  Tải lại
                </button>
              </div>

              {integrations.length ? (
                <div className="mt-[10px] grid grid-cols-3 gap-[6px]">
                  <button
                    onClick={() =>
                      setSelectedIntegrationIds(
                        integrations.map((integration) => integration.id)
                      )
                    }
                    className="rounded-[8px] bg-[#f0f0f3] px-[8px] py-[7px] text-[12px] font-semibold"
                  >
                    FB + IG
                  </button>
                  <button
                    onClick={() =>
                      setSelectedIntegrationIds(
                        integrations
                          .filter(
                            (integration) =>
                              integrationProvider(integration) === 'Facebook'
                          )
                          .map((integration) => integration.id)
                      )
                    }
                    className="rounded-[8px] bg-[#f0f0f3] px-[8px] py-[7px] text-[12px] font-semibold"
                  >
                    Chỉ FB
                  </button>
                  <button
                    onClick={() =>
                      setSelectedIntegrationIds(
                        integrations
                          .filter(
                            (integration) =>
                              integrationProvider(integration) === 'Instagram'
                          )
                          .map((integration) => integration.id)
                      )
                    }
                    className="rounded-[8px] bg-[#f0f0f3] px-[8px] py-[7px] text-[12px] font-semibold"
                  >
                    Chỉ IG
                  </button>
                </div>
              ) : null}

              {selectedIntegrations.length ? (
                <div className="mt-[10px] rounded-[10px] bg-[#f7f7f8] px-[10px] py-[9px] text-[12px] text-[#33343a]">
                  Sẽ đăng lên:{' '}
                  <span className="font-semibold">
                    {selectedIntegrations
                      .map(
                        (integration) =>
                          `${integration.name} (${integrationProvider(integration)})`
                      )
                      .join(' + ')}
                  </span>
                </div>
              ) : (
                <div className="mt-[10px] rounded-[10px] bg-[#fff7ed] px-[10px] py-[9px] text-[12px] text-[#9a3412]">
                  Chưa chọn kênh đăng. Bấm Tải lại hoặc kiểm tra mục Tích hợp.
                </div>
              )}

              {!integrations.length ? (
                <div className="mt-[10px] rounded-[10px] border border-dashed border-[#dedee3] px-[10px] py-[12px] text-[12px] text-[#777981]">
                  Chưa tải được kênh Facebook/Instagram đang hoạt động.
                </div>
              ) : null}

              <div className="mt-[10px] text-[12px] text-[#777981]">
                Chọn nhóm kênh trước khi bấm Tự tải & lên lịch.
              </div>
              <div className="mt-[10px] flex flex-col gap-[8px]">
                {integrations.map((integration) => (
                  <label
                    key={integration.id}
                    className="flex cursor-pointer items-center gap-[10px] rounded-[10px] border border-[#ececf0] px-[10px] py-[9px]"
                  >
                    <input
                      type="checkbox"
                      checked={selectedIntegrationIds.includes(integration.id)}
                      onChange={(event) => {
                        setSelectedIntegrationIds((current) =>
                          event.target.checked
                            ? [...current, integration.id]
                            : current.filter((id) => id !== integration.id)
                        );
                      }}
                    />
                    {integration.picture ? (
                      <img
                        src={integration.picture}
                        className="h-[28px] w-[28px] rounded-[6px] object-cover"
                        alt=""
                      />
                    ) : null}
                    <div className="min-w-0">
                      <div className="truncate text-[14px] font-medium">
                        {integration.name}
                      </div>
                      <div className="text-[12px] text-[#777981]">
                        {integrationProvider(integration)}
                      </div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div className="h-px bg-[#eeeeF1]" />

            <div>
              <div className="text-[13px] font-semibold text-[#6f7177]">
                Lịch đăng
              </div>
              <label className="mt-[10px] block text-[12px] text-[#777981]">
                Bắt đầu
              </label>
              <input
                value={startAt}
                onChange={(event) => setStartAt(event.target.value)}
                type="datetime-local"
                className="mt-[5px] w-full rounded-[9px] border border-[#dedee3] bg-white px-[10px] py-[9px] text-[14px]"
              />
              <label className="mt-[10px] block text-[12px] text-[#777981]">
                Cách nhau
              </label>
              <select
                value={intervalMinutes}
                onChange={(event) => setIntervalMinutes(Number(event.target.value))}
                className="mt-[5px] w-full rounded-[9px] border border-[#dedee3] bg-white px-[10px] py-[9px] text-[14px]"
              >
                <option value={30}>30 phút</option>
                <option value={60}>1 tiếng</option>
                <option value={90}>1 tiếng 30 phút</option>
                <option value={120}>2 tiếng</option>
              </select>
            </div>
          </aside>

          <main className="flex flex-col gap-[14px] rounded-[14px] border border-[#e7e7ea] bg-white p-[18px]">
            <div className="flex items-center justify-between">
              <div className="flex rounded-[10px] bg-[#f0f0f3] p-[3px]">
                <button
                  onClick={() => setMode('local')}
                  className={`rounded-[8px] px-[14px] py-[8px] text-[14px] font-medium ${
                    mode === 'local' ? 'bg-white shadow-sm' : 'text-[#6f7177]'
                  }`}
                >
                  Kéo file
                </button>
                <button
                  onClick={() => setMode('drive')}
                  className={`rounded-[8px] px-[14px] py-[8px] text-[14px] font-medium ${
                    mode === 'drive' ? 'bg-white shadow-sm' : 'text-[#6f7177]'
                  }`}
                >
                  Google Drive
                </button>
              </div>
              <div className="text-[13px] text-[#777981]">
                {rows.length
                  ? `${rows.length} video, còn ${pendingCount} chưa xong`
                  : 'Chưa có video'}
              </div>
            </div>

            {mode === 'local' ? (
              <div
                onDragOver={(event) => event.preventDefault()}
                onDrop={handleDrop}
                className="flex min-h-[170px] flex-col items-center justify-center rounded-[14px] border border-dashed border-[#d8d8de] bg-[#fafafa] px-[24px] text-center"
              >
                <div className="text-[18px] font-semibold">Kéo nhiều video vào đây</div>
                <div className="mt-[6px] text-[13px] text-[#74767e]">
                  Hỗ trợ .mp4, .mov, .webm. Không giới hạn tổng dung lượng batch.
                </div>
                <label className="mt-[16px] cursor-pointer rounded-[9px] bg-[#111113] px-[14px] py-[10px] text-[14px] font-semibold text-white">
                  Chọn video
                  <input
                    className="hidden"
                    type="file"
                    multiple
                    accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm"
                    onChange={handleFileInput}
                  />
                </label>
              </div>
            ) : (
              <div className="rounded-[14px] border border-[#ececf0] bg-[#fafafa] p-[16px]">
                <div className="flex items-center justify-between gap-[10px]">
                  <div>
                    <div className="text-[18px] font-semibold">Nhập từ Google Drive</div>
                    <div className="mt-[4px] text-[13px] text-[#74767e]">
                      All-in-one trong Postiz, theo chuẩn SO9: Drive là nguồn video, Postiz scan rồi lên lịch Reels.
                    </div>
                  </div>
                  <button
                    onClick={connectDrive}
                    disabled={!driveConfigured || driveConnected}
                    className="rounded-[9px] border border-[#dedee3] bg-white px-[12px] py-[9px] text-[13px] font-semibold disabled:text-[#9a9ca3]"
                  >
                    {driveConnected ? 'Đã kết nối' : 'Kết nối Drive'}
                  </button>
                </div>
                <div className="mt-[14px] grid grid-cols-4 gap-[8px]">
                  {driveReadiness.map(({ label, ok }) => (
                    <div
                      key={String(label)}
                      className={`rounded-[9px] px-[10px] py-[8px] text-[12px] font-semibold ${
                        ok
                          ? 'bg-[#ecfdf3] text-[#067647]'
                          : 'bg-[#fff7ed] text-[#b45309]'
                      }`}
                    >
                      {label}: {ok ? 'OK' : 'Chưa'}
                    </div>
                  ))}
                </div>

                {!driveConfigured ? (
                  <div className="mt-[14px] rounded-[12px] border border-[#ececf0] bg-white p-[12px]">
                    <div className="text-[13px] font-semibold text-[#33343a]">
                      Google OAuth trong Postiz
                    </div>
                    <div className="mt-[6px] text-[12px] text-[#74767e]">
                      Tạo OAuth Client loại Web application và thêm Redirect URI này:
                    </div>
                    <div className="mt-[8px] rounded-[8px] bg-[#f5f5f7] px-[9px] py-[8px] text-[12px] text-[#33343a]">
                      {driveRedirectUri || 'Đang tải redirect URI...'}
                    </div>
                    <div className="mt-[10px] grid grid-cols-1 gap-[8px]">
                      <input
                        value={driveClientId}
                        onChange={(event) => setDriveClientId(event.target.value)}
                        placeholder="Google Client ID"
                        className="rounded-[9px] border border-[#dedee3] bg-white px-[10px] py-[10px] text-[14px]"
                      />
                      <input
                        value={driveClientSecret}
                        onChange={(event) =>
                          setDriveClientSecret(event.target.value)
                        }
                        type="password"
                        placeholder="Google Client Secret"
                        className="rounded-[9px] border border-[#dedee3] bg-white px-[10px] py-[10px] text-[14px]"
                      />
                      <button
                        onClick={saveDriveConfig}
                        disabled={loading || !driveClientId || !driveClientSecret}
                        className="rounded-[9px] bg-[#111113] px-[14px] py-[10px] text-[14px] font-semibold text-white disabled:bg-[#c9c9ce]"
                      >
                        Lưu OAuth vào Postiz
                      </button>
                    </div>
                  </div>
                ) : null}

                <div className="mt-[14px] flex gap-[8px]">
                  <input
                    value={driveFolder}
                    onChange={(event) => {
                      setDriveFolder(event.target.value);
                      setDriveScanned(false);
                    }}
                    placeholder="Google Drive folder URL"
                    className="flex-1 rounded-[9px] border border-[#dedee3] bg-white px-[10px] py-[10px] text-[14px]"
                  />
                  <button
                    onClick={saveDriveFolder}
                    disabled={loading || !driveFolder}
                    className="rounded-[9px] border border-[#dedee3] bg-white px-[14px] py-[10px] text-[14px] font-semibold disabled:text-[#9a9ca3]"
                  >
                    Lưu
                  </button>
                  <button
                    onClick={scanDrive}
                    disabled={loading || !driveConnected || !driveFolder}
                    className="rounded-[9px] bg-[#111113] px-[14px] py-[10px] text-[14px] font-semibold text-white disabled:bg-[#c9c9ce]"
                  >
                    Test / Quét
                  </button>
                </div>
                {!driveConfigured ? (
                  <div className="mt-[10px] text-[12px] text-[#b45309]">
                    Chưa cấu hình Google OAuth trong Postiz.
                  </div>
                ) : null}
                {driveConfigured && !driveConnected ? (
                  <div className="mt-[10px] text-[12px] text-[#b45309]">
                    OAuth đã có. Bấm Kết nối Drive để cấp quyền read-only.
                  </div>
                ) : null}
              </div>
            )}

            {message ? (
              <div className="rounded-[10px] bg-[#f5f5f7] px-[12px] py-[10px] text-[13px] text-[#33343a]">
                {message}
              </div>
            ) : null}

            <div className="overflow-hidden rounded-[12px] border border-[#ececf0]">
              <table className="w-full border-collapse text-left text-[13px]">
                <thead className="bg-[#fafafa] text-[#777981]">
                  <tr>
                    <th className="w-[50px] px-[12px] py-[11px]">#</th>
                    <th className="w-[120px] px-[12px] py-[11px]">Trạng thái</th>
                    <th className="px-[12px] py-[11px]">Tiêu đề</th>
                    <th className="w-[130px] px-[12px] py-[11px]">Dung lượng</th>
                    <th className="w-[190px] px-[12px] py-[11px]">Giờ lên lịch</th>
                    <th className="w-[160px] px-[12px] py-[11px]">Kênh</th>
                    <th className="w-[110px] px-[12px] py-[11px]">Hành động</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={row.id} className="border-t border-[#ececf0]">
                      <td className="px-[12px] py-[12px] text-[#8b8d94]">
                        {index + 1}
                      </td>
                      <td className="px-[12px] py-[12px]">
                        <div className="font-medium">{statusText[row.status]}</div>
                        {row.status === 'uploading' ? (
                          <div className="mt-[5px] h-[4px] rounded-full bg-[#eeeeF1]">
                            <div
                              className="h-[4px] rounded-full bg-[#111113]"
                              style={{ width: `${row.progress}%` }}
                            />
                          </div>
                        ) : null}
                        {row.error ? (
                          <div className="mt-[4px] text-[12px] text-[#b42318]">
                            {row.error}
                          </div>
                        ) : null}
                      </td>
                      <td className="px-[12px] py-[12px]">
                        <input
                          value={row.title}
                          onChange={(event) =>
                            updateRow(row.id, { title: event.target.value })
                          }
                          className="w-full rounded-[8px] border border-transparent bg-transparent px-[8px] py-[7px] font-medium outline-none focus:border-[#d8d8de] focus:bg-white"
                        />
                      </td>
                      <td className="px-[12px] py-[12px] text-[#60626a]">
                        {formatBytes(row.size)}
                      </td>
                      <td className="px-[12px] py-[12px]">
                        <input
                          value={row.scheduledAt}
                          onChange={(event) =>
                            updateRow(row.id, { scheduledAt: event.target.value })
                          }
                          type="datetime-local"
                          className="w-full rounded-[8px] border border-[#dedee3] px-[8px] py-[7px]"
                        />
                      </td>
                      <td className="px-[12px] py-[12px] text-[#60626a]">
                        {selectedIntegrations.length ? (
                          <div className="flex flex-wrap gap-[5px]">
                            {selectedIntegrations.map((integration) => (
                              <span
                                key={integration.id}
                                title={`${integration.name} (${integrationProvider(
                                  integration
                                )})`}
                                className="rounded-full bg-[#f0f0f3] px-[8px] py-[4px] text-[12px] font-semibold text-[#33343a]"
                              >
                                {shortProvider(integration)}
                              </span>
                            ))}
                          </div>
                        ) : (
                          'Chưa chọn'
                        )}
                      </td>
                      <td className="px-[12px] py-[12px]">
                        {row.status === 'error' ? (
                          <button
                            onClick={() => runBatch(row.id)}
                            className="rounded-[8px] border border-[#dedee3] px-[10px] py-[7px] text-[12px] font-semibold"
                          >
                            Thử lại
                          </button>
                        ) : (
                          <button
                            onClick={() =>
                              setRows((current) =>
                                current.filter((item) => item.id !== row.id)
                              )
                            }
                            disabled={row.status === 'uploading'}
                            className="rounded-[8px] border border-[#dedee3] px-[10px] py-[7px] text-[12px] font-semibold disabled:text-[#aaa]"
                          >
                            Xóa
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {!rows.length ? (
                    <tr>
                      <td colSpan={7} className="px-[12px] py-[44px] text-center text-[#777981]">
                        Chọn video hoặc quét Drive để bắt đầu.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
