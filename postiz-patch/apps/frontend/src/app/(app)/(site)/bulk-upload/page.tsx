import { Metadata } from 'next';
import { BulkUploadComponent } from '@gitroom/frontend/components/bulk-upload/bulk-upload.component';
import { isGeneralServerSide } from '@gitroom/helpers/utils/is.general.server.side';

export const metadata: Metadata = {
  title: `${isGeneralServerSide() ? 'Postiz' : 'Gitroom'} Bulk Upload`,
  description: 'Bulk video upload and scheduling',
};

export default function Page() {
  return <BulkUploadComponent />;
}
