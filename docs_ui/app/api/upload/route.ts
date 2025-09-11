import {
  ALLOWED_FILE_TYPES,
  MAX_FILE_SIZE,
  type UploadResult,
} from '@utils/upload'
import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'

const allowedTypes = Object.keys(ALLOWED_FILE_TYPES)
const allowedExtensions = Object.values(ALLOWED_FILE_TYPES)

export async function POST(
  request: NextRequest
): Promise<NextResponse<UploadResult | { error: string }>> {
  try {
    const formData = await request.formData()
    const chat = formData.get('chat') as string
    const files: File[] = []
    for (const [, value] of formData.entries()) {
      if (value instanceof File) {
        files.push(value)
      }
    }

    if (!chat) {
      return NextResponse.json(
        { error: 'Chat parameter is required' },
        { status: 400 }
      )
    }

    if (!files || files.length === 0) {
      return NextResponse.json({ error: 'No files provided' }, { status: 400 })
    }

    const validatedFiles = files.filter((file) => {
      if (!file || file.size === 0) return false
      if (
        !allowedTypes.includes(file.type) &&
        !allowedExtensions.includes(`.${file.name.split('.').pop()}` as any)
      ) {
        console.warn(
          `Skipping disallowed file type: ${file.name} (${file.type})`
        )
        return false
      }
      if (file.size > MAX_FILE_SIZE) {
        console.warn(
          `Skipping oversized file: ${file.name} (${file.size} bytes)`
        )
        return false
      }
      return true
    })

    if (validatedFiles.length === 0) {
      return NextResponse.json(
        { error: 'No valid files to upload after filtering' },
        { status: 400 }
      )
    }

    const allFilesFormData = new FormData()
    for (const file of validatedFiles) {
      allFilesFormData.append(file.name, file)
    }

    const response = await fetch(`${process.env.RAG_URL}/upload`, {
      method: 'POST',
      body: allFilesFormData,
    })

    if (!response.ok) {
      const errorData = await response.json()
      throw new Error(
        `Failed to upload files: ${response.statusText} - ${JSON.stringify(
          errorData
        )}`
      )
    }

    const resultData = await response.json()
    const result = {
      success: true,
      files: resultData.files.map((name: string) => ({ name })),
      chat,
      message:
        resultData.message ||
        `Successfully processed ${resultData.files.length} file(s)`,
    }
    return NextResponse.json(result, { status: 200 })
  } catch (error) {
    console.error('Upload error:', error)
    const errorMessage =
      error instanceof Error ? error.message : 'An unknown error occurred'
    return NextResponse.json(
      { error: `Internal server error: ${errorMessage}` },
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
