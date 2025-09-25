export interface UploadedFile {
  file: File
  id: string
}

export interface UploadResult {
  success: boolean
  files: Array<{
    name: string
    size: number
    path: string
  }>
  chat: string
  message: string
}

export interface UploadError {
  error: string
}

export type UploadResponse = UploadResult | UploadError

export const ALLOWED_FILE_TYPES = {
  // Documents
  'application/pdf': '.pdf',
  'application/msword': '.doc',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
    '.docx',
  'application/vnd.oasis.opendocument.text': '.odt',
  'application/rtf': '.rtf',
  'application/epub+zip': '.epub',
  'application/vnd.ms-powerpoint': '.ppt',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation':
    '.pptx',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',

  // Text formats
  'text/plain': '.txt',
  'text/markdown': '.md',
  'text/html': '.html',
  'text/xml': '.xml',
  'text/csv': '.csv',
  'text/tab-separated-values': '.tsv',
  'text/x-rst': '.rst',
  'text/org': '.org',

  // Email
  'message/rfc822': '.eml',
  'application/vnd.ms-outlook': '.msg',

  // Images
  'image/bmp': '.bmp',
  'image/heic': '.heic',
  'image/jpeg': '.jpg',
  'image/png': '.png',
  'image/tiff': '.tiff',

  // Audio
  'audio/wav': '.wav',
  'audio/mpeg': '.mp3',
  'audio/aiff': '.aiff',
  'audio/aac': '.aac',
  'audio/ogg': '.ogg',
  'audio/flac': '.flac',
} as const

export const MAX_FILE_SIZE = 200 * 1024 * 1024 // 200MB
export const ACCEPTED_EXTENSIONS =
  '.aac,.aiff,.bmp,.csv,.doc,.docx,.eml,.epub,.flac,.heic,.html,.jpeg,.jpg,.md,.mp3,.msg,.odt,.ogg,.org,.pdf,.png,.ppt,.pptx,.rtf,.rst,.tiff,.tsv,.txt,.wav,.xml,.xlsx,.zip'
