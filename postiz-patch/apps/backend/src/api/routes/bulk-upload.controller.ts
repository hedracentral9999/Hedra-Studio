import {
  BadRequestException,
  Body,
  Controller,
  Get,
  Post,
  Query,
  Res,
  UploadedFile,
  UseInterceptors,
  UsePipes,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { Response } from 'express';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { extname, join } from 'path';
import { google } from 'googleapis';
import { Organization } from '@prisma/client';
import { ApiTags } from '@nestjs/swagger';
import { GetOrgFromRequest } from '@gitroom/nestjs-libraries/user/org.from.request';
import { MediaService } from '@gitroom/nestjs-libraries/database/prisma/media/media.service';
import { PostsService } from '@gitroom/nestjs-libraries/database/prisma/posts/posts.service';
import { IntegrationService } from '@gitroom/nestjs-libraries/database/prisma/integrations/integration.service';
import { CreatePostDto } from '@gitroom/nestjs-libraries/dtos/posts/create.post.dto';
import { UploadFactory } from '@gitroom/nestjs-libraries/upload/upload.factory';
import { CustomFileValidationPipe } from '@gitroom/nestjs-libraries/upload/custom.upload.validation';

type BulkScheduleBody = {
  mediaId: string;
  title: string;
  integrationIds: string[];
  scheduledAt: string;
  hashtags?: string[];
};

type DriveImportBody = {
  fileId: string;
  fileName: string;
  title: string;
  integrationIds: string[];
  scheduledAt: string;
  hashtags?: string[];
};

type DriveConfigBody = {
  clientId?: string;
  clientSecret?: string;
  redirectUri?: string;
  folderUrl?: string;
};

@ApiTags('Bulk upload')
@Controller('/bulk-upload')
export class BulkUploadController {
  private storage = UploadFactory.createStorage();
  private configDir = join('/config', 'bulk-upload');
  private oauthConfigPath = join(this.configDir, 'google-drive-oauth.json');
  private folderConfigPath = join(this.configDir, 'google-drive-folder.json');

  constructor(
    private _mediaService: MediaService,
    private _postsService: PostsService,
    private _integrationService: IntegrationService
  ) {}

  @Get('/health')
  health() {
    return {
      ok: true,
      directUpload: true,
      googleDrive: !!(
        process.env.GOOGLE_DRIVE_CLIENT_ID &&
        process.env.GOOGLE_DRIVE_CLIENT_SECRET
      ),
    };
  }

  @Get('/integrations')
  async integrations(@GetOrgFromRequest() org: Organization) {
    const integrations = await this._integrationService.getIntegrationsList(org.id);

    return {
      integrations: integrations
        .filter(
          (integration: any) =>
            !integration.disabled &&
            !integration.refreshNeeded &&
            this.isPublishIntegration(integration)
        )
        .map((integration: any) => ({
          id: integration.id,
          name: integration.name,
          identifier:
            integration.providerIdentifier ||
            integration.identifier ||
            integration.type ||
            '',
          providerIdentifier:
            integration.providerIdentifier || integration.identifier || '',
          type: integration.type || '',
          picture: integration.picture || '/no-picture.jpg',
          disabled: !!integration.disabled,
          refreshNeeded: !!integration.refreshNeeded,
        })),
    };
  }

  @Post('/upload')
  @UseInterceptors(FileInterceptor('file'))
  @UsePipes(new CustomFileValidationPipe())
  async upload(
    @GetOrgFromRequest() org: Organization,
    @UploadedFile('file') file: Express.Multer.File
  ) {
    if (!file) {
      throw new BadRequestException('Missing file');
    }

    const originalName = file.originalname;
    const uploadedFile = await this.storage.uploadFile(file);
    return this._mediaService.saveFile(
      org.id,
      uploadedFile.originalname,
      uploadedFile.path,
      originalName
    );
  }

  @Post('/schedule')
  async schedule(
    @GetOrgFromRequest() org: Organization,
    @Body() body: BulkScheduleBody
  ) {
    return this.scheduleMedia(
      org,
      body.mediaId,
      body.title,
      body.integrationIds,
      body.scheduledAt,
      body.hashtags
    );
  }

  @Get('/drive/status')
  driveStatus(@GetOrgFromRequest() org: Organization) {
    const oauth = this.readDriveOAuthConfig();
    const folder = this.readDriveFolderConfig();
    const configured = !!(oauth.clientId && oauth.clientSecret);
    const connected = existsSync(this.driveTokenPath(org.id));
    const folderConfigured = !!folder.folderUrl;

    return {
      configured,
      connected,
      folderConfigured,
      folderUrl: folder.folderUrl || '',
      redirectUri: oauth.redirectUri || this.defaultDriveRedirectUri(),
      readiness: {
        oauthClient: configured,
        driveToken: connected,
        driveFolder: folderConfigured,
        so9DriveReady: configured && connected && folderConfigured,
      },
    };
  }

  @Post('/drive/config')
  driveConfig(@Body() body: DriveConfigBody) {
    const currentOauth = this.readDriveOAuthConfig();
    const nextOauth = {
      clientId: body.clientId?.trim() || currentOauth.clientId || '',
      clientSecret: body.clientSecret?.trim() || currentOauth.clientSecret || '',
      redirectUri: body.redirectUri?.trim() || currentOauth.redirectUri || this.defaultDriveRedirectUri(),
    };

    if (!nextOauth.clientId || !nextOauth.clientSecret) {
      throw new BadRequestException('Missing Google OAuth Client ID or Client Secret');
    }

    mkdirSync(this.configDir, { recursive: true });
    writeFileSync(this.oauthConfigPath, JSON.stringify(nextOauth, null, 2));

    if (body.folderUrl?.trim()) {
      this.writeDriveFolder(body.folderUrl.trim());
    }

    return {
      ok: true,
      configured: true,
      folderConfigured: !!(body.folderUrl?.trim() || this.readDriveFolderConfig().folderUrl),
      redirectUri: nextOauth.redirectUri,
    };
  }

  @Post('/drive/folder')
  driveFolder(@Body('folderUrl') folderUrl: string) {
    if (!folderUrl?.trim()) {
      throw new BadRequestException('Missing Google Drive folder URL');
    }

    this.extractDriveFolderId(folderUrl);
    this.writeDriveFolder(folderUrl.trim());
    return {
      ok: true,
      folderUrl: folderUrl.trim(),
    };
  }

  @Get('/drive/auth-url')
  driveAuthUrl() {
    const oauth = this.getDriveClient();
    return {
      url: oauth.generateAuthUrl({
        access_type: 'offline',
        prompt: 'consent',
        scope: ['https://www.googleapis.com/auth/drive.readonly'],
      }),
    };
  }

  @Get('/drive/callback')
  async driveCallback(
    @GetOrgFromRequest() org: Organization,
    @Query('code') code: string,
    @Res() res: Response
  ) {
    if (!code) {
      throw new BadRequestException('Missing Google authorization code');
    }

    const oauth = this.getDriveClient();
    const { tokens } = await oauth.getToken(code);
    mkdirSync(this.configDir, { recursive: true });
    writeFileSync(this.driveTokenPath(org.id), JSON.stringify(tokens, null, 2));
    res.redirect(`${process.env.FRONTEND_URL || ''}/bulk-upload?drive=connected`);
  }

  @Post('/drive/scan')
  async driveScan(
    @GetOrgFromRequest() org: Organization,
    @Body('folderUrl') folderUrl: string
  ) {
    const finalFolderUrl = folderUrl || this.readDriveFolderConfig().folderUrl;
    const folderId = this.extractDriveFolderId(finalFolderUrl);
    const drive = this.getDrive(org.id);
    const files = await drive.files.list({
      q: `'${folderId}' in parents and trashed = false`,
      pageSize: 200,
      fields: 'files(id,name,mimeType,size,modifiedTime,thumbnailLink,webViewLink)',
      orderBy: 'name',
    });

    return {
      folderId,
      files: (files.data.files || [])
        .filter((file) => this.isVideoFile(file.name || '', file.mimeType || ''))
        .map((file) => ({
          id: file.id,
          name: file.name,
          title: this.titleFromName(file.name || ''),
          mimeType: file.mimeType,
          size: file.size ? Number(file.size) : null,
          modifiedTime: file.modifiedTime,
          thumbnailLink: file.thumbnailLink,
          webViewLink: file.webViewLink,
        })),
    };
  }

  @Post('/drive/import')
  async driveImport(
    @GetOrgFromRequest() org: Organization,
    @Body() body: DriveImportBody
  ) {
    const drive = this.getDrive(org.id);
    const file = await drive.files.get(
      { fileId: body.fileId, alt: 'media' },
      { responseType: 'arraybuffer' }
    );
    const buffer = Buffer.from(file.data as ArrayBuffer);
    const mimeType = file.headers?.['content-type'] || 'video/mp4';
    const uploaded = await this.storage.uploadFile({
      buffer,
      originalname: body.fileName,
      mimetype: Array.isArray(mimeType) ? mimeType[0] : mimeType,
    } as Express.Multer.File);
    const media = await this._mediaService.saveFile(
      org.id,
      uploaded.originalname,
      uploaded.path,
      body.fileName
    );

    return this.scheduleMedia(
      org,
      media.id,
      body.title || this.titleFromName(body.fileName),
      body.integrationIds,
      body.scheduledAt,
      body.hashtags
    );
  }

  private async scheduleMedia(
    org: Organization,
    mediaId: string,
    title: string,
    integrationIds: string[],
    scheduledAt: string,
    hashtags: string[] = []
  ) {
    if (!mediaId || !scheduledAt || !Array.isArray(integrationIds) || !integrationIds.length) {
      throw new BadRequestException('Missing schedule data');
    }

    const media = await this._mediaService.getMediaById(mediaId);
    if (!media || media.organizationId !== org.id) {
      throw new BadRequestException('Media not found');
    }

    const cleanTitle = (title || media.originalName || media.name || '')
      .replace(/\.[^/.]+$/, '')
      .trim();
    const cleanCaption = this.buildCaption(cleanTitle, hashtags);
    const orgIntegrations = await this._integrationService.getIntegrationsList(org.id);
    const integrationsById = new Map(
      orgIntegrations.map((integration: any) => [integration.id, integration])
    );

    const group = `bulk-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const rawBody = {
      type: 'schedule' as const,
      shortLink: false,
      date: scheduledAt,
      tags: [],
      posts: integrationIds.map((id) => ({
        integration: { id },
        group,
        value: [
          {
            id: '',
            content: cleanCaption,
            delay: 0,
            image: [
              {
                id: media.id,
                path: media.path,
                alt: media.alt,
                thumbnail: media.thumbnail,
              },
            ],
          },
        ],
        settings: this.settingsForIntegration(integrationsById.get(id) || { id }),
      })),
    };

    const mapped = await this._postsService.mapTypeToPost(
      rawBody as unknown as CreatePostDto,
      org.id
    );
    return this._postsService.createPost(org.id, mapped, 'WEB');
  }

  private buildCaption(title: string, hashtags: string[] = []) {
    const defaults = ['#boxphonefarm', '#congnghe', '#phukien', '#review'];
    const cleanHashtags = [...(hashtags.length ? hashtags : defaults)]
      .map((tag) => String(tag || '').trim())
      .filter(Boolean)
      .map((tag) => (tag.startsWith('#') ? tag : `#${tag}`))
      .map((tag) => tag.replace(/[^\p{L}\p{N}_#]/gu, '').toLowerCase())
      .filter((tag, index, array) => tag.length > 1 && array.indexOf(tag) === index)
      .slice(0, 8);
    return cleanHashtags.length ? `${title}\n\n${cleanHashtags.join(' ')}` : title;
  }

  private settingsForIntegration(integration: any) {
    const source = [
      integration.providerIdentifier,
      integration.identifier,
      integration.type,
      integration.name,
      integration.id,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();

    if (source.includes('instagram')) {
      return {
        __type: 'instagram',
        post_type: 'reel',
        is_trial_reel: false,
        collaborators: [],
      };
    }

    if (source.includes('facebook')) {
      return {
        __type: 'facebook',
      };
    }

    return {
      __type:
        integration.providerIdentifier ||
        integration.identifier ||
        integration.type ||
        'unknown',
    };
  }

  private getDriveClient() {
    const config = this.readDriveOAuthConfig();
    if (!config.clientId || !config.clientSecret) {
      throw new BadRequestException('Google Drive OAuth is not configured');
    }

    return new google.auth.OAuth2(
      config.clientId,
      config.clientSecret,
      config.redirectUri || this.defaultDriveRedirectUri()
    );
  }

  private getDrive(orgId: string) {
    const tokenPath = this.driveTokenPath(orgId);
    if (!existsSync(tokenPath)) {
      throw new BadRequestException('Google Drive is not connected');
    }

    const oauth = this.getDriveClient();
    oauth.setCredentials(JSON.parse(readFileSync(tokenPath, 'utf8')));
    return google.drive({ version: 'v3', auth: oauth });
  }

  private readDriveOAuthConfig() {
    const fileConfig = existsSync(this.oauthConfigPath)
      ? JSON.parse(readFileSync(this.oauthConfigPath, 'utf8'))
      : {};
    return {
      clientId: process.env.GOOGLE_DRIVE_CLIENT_ID || fileConfig.clientId || '',
      clientSecret:
        process.env.GOOGLE_DRIVE_CLIENT_SECRET || fileConfig.clientSecret || '',
      redirectUri:
        process.env.GOOGLE_DRIVE_REDIRECT_URI ||
        fileConfig.redirectUri ||
        this.defaultDriveRedirectUri(),
    };
  }

  private readDriveFolderConfig() {
    if (!existsSync(this.folderConfigPath)) {
      return { folderUrl: process.env.GOOGLE_DRIVE_FOLDER_ID || '' };
    }

    return JSON.parse(readFileSync(this.folderConfigPath, 'utf8'));
  }

  private writeDriveFolder(folderUrl: string) {
    mkdirSync(this.configDir, { recursive: true });
    writeFileSync(this.folderConfigPath, JSON.stringify({ folderUrl }, null, 2));
  }

  private driveTokenPath(orgId: string) {
    return join(this.configDir, `google-drive-token-${orgId}.json`);
  }

  private defaultDriveRedirectUri() {
    return (
      process.env.GOOGLE_DRIVE_REDIRECT_URI ||
      `${process.env.FRONTEND_URL || ''}/api/bulk-upload/drive/callback`
    );
  }

  private extractDriveFolderId(folderUrl: string) {
    const trimmed = (folderUrl || '').trim();
    const folderMatch = trimmed.match(/\/folders\/([a-zA-Z0-9_-]+)/);
    const idMatch = trimmed.match(/[?&]id=([a-zA-Z0-9_-]+)/);
    const id = folderMatch?.[1] || idMatch?.[1] || trimmed;
    if (!id || !/^[a-zA-Z0-9_-]+$/.test(id)) {
      throw new BadRequestException('Invalid Google Drive folder URL');
    }
    return id;
  }

  private titleFromName(name: string) {
    return name.replace(/\.[^/.]+$/, '').trim();
  }

  private isVideoFile(name: string, mimeType: string) {
    const ext = extname(name).toLowerCase();
    return (
      mimeType.startsWith('video/') ||
      ['.mp4', '.mov', '.webm', '.mkv'].includes(ext)
    );
  }

  private isPublishIntegration(integration: any) {
    const source = [
      integration.providerIdentifier,
      integration.identifier,
      integration.type,
      integration.name,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();

    return source.includes('facebook') || source.includes('instagram');
  }
}
