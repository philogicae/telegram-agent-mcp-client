import { existsSync } from 'node:fs'
import { mkdir, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'

interface UploadResult {
  success: boolean
  files: Array<{
    name: string
    size: number
    path: string
  }>
  chat: string
  message: string
}

export async function POST(
  request: NextRequest
): Promise<NextResponse<UploadResult | { error: string }>> {
  try {
    const formData = await request.formData()

    const chat = formData.get('chat') as string
    const files = formData.getAll('files') as File[]

    if (!chat) {
      return NextResponse.json(
        { error: 'Chat parameter is required' },
        { status: 400 }
      )
    }

    if (!files || files.length === 0) {
      return NextResponse.json({ error: 'No files provided' }, { status: 400 })
    }

    // Create uploads directory if it doesn't exist
    const uploadsDir = join(process.cwd(), 'uploads')
    const chatDir = join(uploadsDir, chat)

    if (!existsSync(uploadsDir)) {
      await mkdir(uploadsDir, { recursive: true })
    }

    if (!existsSync(chatDir)) {
      await mkdir(chatDir, { recursive: true })
    }

    const uploadedFiles = []

    for (const file of files) {
      if (!file || file.size === 0) {
        continue
      }

      // Validate file type
      const allowedTypes = [
        // Documents
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.oasis.opendocument.text',
        'application/epub+zip',
        'application/rtf',
        'application/zip',

        // Text formats
        'text/plain',
        'text/markdown',
        'text/html',
        'text/xml',
        'text/csv',
        'text/tab-separated-values',
        'text/x-rst',
        'text/org',

        // Images
        'image/jpeg',
        'image/png',
        'image/bmp',
        'image/tiff',
        'image/heic',

        // Email
        'message/rfc822',
        'application/vnd.ms-outlook',
      ]

      if (!allowedTypes.includes(file.type)) {
        return NextResponse.json(
          {
            error: `File type ${file.type} is not allowed. Please upload: PDF, BMP, EML, HEIC, HTML, JPG, JPEG, TIFF, PNG, TXT, XML, CSV, DOC, DOCX, EPUB, MD, MSG, ODT, ORG, PPT, PPTX, RTF, RST, TSV, XLSX, ZIP`,
          },
          { status: 400 }
        )
      }

      // Validate file size (max 10MB)
      const maxSize = 10 * 1024 * 1024 // 10MB
      if (file.size > maxSize) {
        return NextResponse.json(
          {
            error: `File ${file.name} is too large. Maximum size is 10MB`,
          },
          { status: 400 }
        )
      }

      // Create unique filename to avoid conflicts
      const timestamp = Date.now()
      const randomSuffix = Math.random().toString(36).substring(2, 8)
      const fileExtension = file.name.split('.').pop()
      const uniqueFileName = `${timestamp}_${randomSuffix}.${fileExtension}`

      const filePath = join(chatDir, uniqueFileName)

      try {
        const bytes = await file.arrayBuffer()
        const buffer = Buffer.from(bytes)
        await writeFile(filePath, buffer)

        uploadedFiles.push({
          name: file.name,
          size: file.size,
          path: filePath,
        })
      } catch (fileError) {
        console.error(`Error saving file ${file.name}:`, fileError)
        return NextResponse.json(
          {
            error: `Failed to save file ${file.name}`,
          },
          { status: 500 }
        )
      }
    }

    const result: UploadResult = {
      success: true,
      files: uploadedFiles,
      chat,
      message: `Successfully uploaded ${uploadedFiles.length} file${uploadedFiles.length === 1 ? '' : 's'}`,
    }

    return NextResponse.json(result, { status: 200 })
  } catch (error) {
    console.error('Upload error:', error)
    return NextResponse.json(
      {
        error: 'Internal server error during file upload',
      },
      { status: 500 }
    )
  }
}

export async function GET() {
  return NextResponse.json(
    {
      error: 'Method not allowed. Use POST to upload files.',
    },
    { status: 405 }
  )
}
