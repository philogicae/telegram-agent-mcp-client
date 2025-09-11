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
  'application/vnd.ms-powerpoint': '.ppt',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation':
    '.pptx',
  'application/vnd.ms-excel': '.xlsx',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
  'application/vnd.oasis.opendocument.text': '.odt',
  'application/epub+zip': '.epub',
  'application/rtf': '.rtf',
  'application/zip': '.zip',

  // Text formats
  'text/plain': '.txt',
  'text/markdown': '.md',
  'text/html': '.html',
  'text/xml': '.xml',
  'text/csv': '.csv',
  'text/tab-separated-values': '.tsv',
  'text/x-rst': '.rst',
  'text/org': '.org',

  // Images
  'image/jpeg': '.jpg',
  'image/png': '.png',
  'image/bmp': '.bmp',
  'image/tiff': '.tiff',
  'image/heic': '.heic',

  // Email
  'message/rfc822': '.eml',
  'application/vnd.ms-outlook': '.msg',
} as const

export const MAX_FILE_SIZE = 200 * 1024 * 1024 // 200MB
export const ACCEPTED_EXTENSIONS =
  '.pdf,.bmp,.eml,.heic,.html,.jpg,.jpeg,.tiff,.png,.txt,.xml,.csv,.doc,.docx,.epub,.md,.msg,.odt,.org,.ppt,.pptx,.rtf,.rst,.tsv,.xlsx,.zip'
