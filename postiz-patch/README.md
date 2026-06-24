# Postiz All-in-one Bulk Upload Patch

Patch nay dua Google Drive OAuth vao Postiz Bulk Upload, lay SO9 lam chuan van hanh:

- Postiz luu Google OAuth Client ID/Secret trong `/config/bulk-upload/google-drive-oauth.json`.
- Token Drive luu theo organization tai `/config/bulk-upload/google-drive-token-<orgId>.json`.
- Folder Drive luu tai `/config/bulk-upload/google-drive-folder.json`.
- Trang `Tải hàng loạt` co readiness: OAuth, Token, Folder, Scan.
- Drive scan/import va local upload deu tao payload video-first/Reels: Facebook `__type=facebook`, Instagram `__type=instagram`, `post_type=reel`.

## Apply vao source Postiz

Copy cac file trong patch vao checkout source Postiz tuong ung:

```sh
cp apps/backend/src/api/routes/bulk-upload.controller.ts /path/to/postiz/apps/backend/src/api/routes/bulk-upload.controller.ts
cp apps/backend/src/api/api.module.ts /path/to/postiz/apps/backend/src/api/api.module.ts
cp apps/frontend/src/components/bulk-upload/bulk-upload.component.tsx /path/to/postiz/apps/frontend/src/components/bulk-upload/bulk-upload.component.tsx
cp apps/frontend/src/app/'(app)'/'(site)'/bulk-upload/page.tsx /path/to/postiz/apps/frontend/src/app/'(app)'/'(site)'/bulk-upload/page.tsx
cp apps/frontend/src/components/layout/top.menu.tsx /path/to/postiz/apps/frontend/src/components/layout/top.menu.tsx
```

Sau do build custom image Postiz va deploy thay cho `ghcr.io/gitroomhq/postiz-app:latest`.

## Setup tren UI

1. Mo Postiz -> `Tải hàng loạt` -> tab `Google Drive`.
2. Tao Google OAuth Client loai `Web application`.
3. Them Redirect URI hien tren Postiz, thuong la:

```text
https://postiz.boxphonefarm.com.vn/api/bulk-upload/drive/callback
```

4. Dan Client ID/Secret vao Postiz, bam `Lưu OAuth vào Postiz`.
5. Bam `Kết nối Drive`, dang nhap tai khoan Drive dung chung va cap quyen read-only.
6. Dan Drive folder URL, bam `Lưu`, roi `Test / Quét`.
7. Khi readiness dat `OAuth`, `Token`, `Folder`, `Scan`, moi chay batch.
