import { useRef, useState } from 'react';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { Avatar } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';

/** What the API accepts, mirrored from `ALLOWED_IMAGE_TYPES` in avatar_storage.py. */
const ACCEPTED = ['image/png', 'image/jpeg', 'image/webp'];
/** Mirrors `avatar_max_bytes`. Checked here so an oversized file never leaves the device. */
const MAX_BYTES = 2 * 1024 * 1024;

export interface AvatarUploadProps {
  name: string;
  avatarUrl: string | null;
  onChange: (avatarUrl: string | null) => void;
}

/**
 * Choose or clear a profile picture.
 *
 * **Not mounted anywhere yet, and that is deliberate.** No object store is configured in
 * any environment, so `POST /auth/me/avatar` answers 503 everywhere — see
 * `apps/api/src/services/avatar_storage.py` for the three things that must be true before
 * a backend may be enabled. Shipping a visible control that always fails would be worse
 * for members than shipping none, so this mounts into `SettingsPage` (as a `SectionCard`
 * titled "Profile picture", beside Timezone) in the batch that wires a real backend.
 *
 * The image is sent as the **raw request body** typed by `Content-Type`, not a multipart
 * form: one file needs no envelope, and it keeps `python-multipart` off the API's
 * dependency list.
 */
export function AvatarUpload({ name, avatarUrl, onChange }: AvatarUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  async function handleFile(file: File) {
    if (!ACCEPTED.includes(file.type)) {
      toast.error('Choose a PNG, JPEG or WebP image');
      return;
    }
    if (file.size > MAX_BYTES) {
      toast.error(`Image must be under ${MAX_BYTES / 1024 / 1024} MB`);
      return;
    }

    setBusy(true);
    try {
      const player = await apiFetch<{ avatar_url: string | null }>('/api/v1/auth/me/avatar', {
        method: 'POST',
        headers: { 'Content-Type': file.type },
        body: file,
      });
      onChange(player.avatar_url);
      toast.success('Profile picture updated');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not upload that image');
    } finally {
      setBusy(false);
      // Clear the input so choosing the same file again still fires a change event.
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  async function handleClear() {
    setBusy(true);
    try {
      await apiFetch('/api/v1/auth/me/avatar', { method: 'DELETE' });
      onChange(null);
      toast.success('Profile picture removed');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not remove that image');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-4">
      {/* The initials fallback is the normal state, not an error state — most members
          never set a picture, and `Avatar` already falls back on a failed load too. */}
      <Avatar name={name} size="lg" src={avatarUrl} />

      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED.join(',')}
          className="sr-only"
          aria-label="Choose a profile picture"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleFile(file);
          }}
        />
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
        >
          {avatarUrl ? 'Change picture' : 'Add a picture'}
        </Button>
        {avatarUrl && (
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => void handleClear()}>
            Remove
          </Button>
        )}
      </div>
    </div>
  );
}
