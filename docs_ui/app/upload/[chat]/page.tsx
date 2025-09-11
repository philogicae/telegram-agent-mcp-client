'use client'
import { Button, Card, CardBody, Progress } from '@heroui/react'
import {
  ACCEPTED_EXTENSIONS,
  ALLOWED_FILE_TYPES,
  MAX_FILE_SIZE,
} from '@utils/upload'
import { use, useEffect, useRef, useState } from 'react'
import {
  FiAlertCircle,
  FiCheckCircle,
  FiFile,
  FiUpload,
  FiX,
} from 'react-icons/fi'

interface UploadedFile {
  file: File
  id: string
}

export default function Upload({
  params,
}: {
  params: Promise<{ chat: string }>
}) {
  const { chat } = use(params)
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [isDragOver, setIsDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const validateFiles = (fileList: File[]) => {
    const allowedTypes = Object.keys(ALLOWED_FILE_TYPES)
    const allowedExtensions: string[] = Object.values(ALLOWED_FILE_TYPES)

    const validFiles: File[] = []
    const errors: string[] = []

    fileList.forEach((file) => {
      const fileExtension = `.${file.name.split('.').pop()?.toLowerCase()}`
      const isValidType =
        allowedTypes.includes(file.type) ||
        allowedExtensions.includes(fileExtension)

      if (!isValidType) {
        errors.push(`${file.name}: Unsupported file type`)
        return
      }

      if (file.size > MAX_FILE_SIZE) {
        errors.push(`${file.name}: File too large (max 200MB)`)
        return
      }

      // Check for duplicates
      const isDuplicate = files.some(
        (f) => f.file.name === file.name && f.file.size === file.size
      )
      if (isDuplicate) {
        errors.push(`${file.name}: File already selected`)
        return
      }

      validFiles.push(file)
    })

    return { validFiles, errors }
  }

  const processFiles = (fileList: File[]) => {
    setError(null)
    setSuccess(null)

    const { validFiles, errors } = validateFiles(fileList)

    if (errors.length > 0) {
      setError(errors.join(', '))
    }

    if (validFiles.length > 0) {
      const newFiles = validFiles.map((file) => ({
        file,
        id: Math.random().toString(36).slice(2, 9),
      }))
      setFiles((prev) => [...prev, ...newFiles])

      if (validFiles.length < fileList.length) {
        setSuccess(`${validFiles.length} files added successfully`)
      }
    }
  }

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(event.target.files || [])
    processFiles(selectedFiles)
  }

  const handleDragOver = (event: React.DragEvent) => {
    event.preventDefault()
    event.stopPropagation()
    setIsDragOver(true)
  }

  const handleDragLeave = (event: React.DragEvent) => {
    event.preventDefault()
    event.stopPropagation()
    setIsDragOver(false)
  }

  const handleDrop = (event: React.DragEvent) => {
    event.preventDefault()
    event.stopPropagation()
    setIsDragOver(false)

    const droppedFiles = Array.from(event.dataTransfer.files)
    processFiles(droppedFiles)
  }

  const removeFile = (id: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== id))
    // Reset the file input to allow selecting the same files again
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const clearAllFiles = () => {
    setFiles([])
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
    setError(null)
    setSuccess(null)
  }

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const sizes = ['Bytes', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${Number.parseFloat((bytes / k ** i).toFixed(2))} ${sizes[i]}`
  }

  // Auto-dismiss notifications after 3 seconds
  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => {
        setError(null)
      }, 3000)
      return () => clearTimeout(timer)
    }
  }, [error])

  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => {
        setSuccess(null)
      }, 3000)
      return () => clearTimeout(timer)
    }
  }, [success])

  const handleUpload = async () => {
    if (files.length === 0) return

    setIsUploading(true)
    setUploadProgress(0)
    setError(null)
    setSuccess(null)

    const formData = new FormData()
    formData.append('chat', chat)

    files.forEach(({ file }) => {
      formData.append('files', file)
    })

    try {
      const response = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      })

      const result = await response.json()

      if (!response.ok) {
        throw new Error(result.error || 'Upload failed')
      }

      setSuccess(result.message)
      setFiles([])
      setUploadProgress(100)

      setTimeout(() => {
        setUploadProgress(0)
      }, 2000)
    } catch (error) {
      const errorMessage =
        error instanceof Error
          ? error.message
          : 'Upload failed. Please try again.'
      setError(errorMessage)
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <div className="flex flex-col w-full h-full items-center justify-center overflow-auto px-4">
      {/* Popup Notifications */}
      {error && (
        <div className="fixed bottom-4 right-4 z-50 animate-in slide-in-from-right-full">
          <Card className="border-red-600 bg-red-100 dark:border-red-400 dark:bg-red-900/50 shadow-lg">
            <CardBody className="p-4">
              <div className="flex items-center space-x-2 text-red-900 dark:text-red-200">
                <FiAlertCircle className="h-5 w-5 flex-shrink-0" />
                <p className="font-bold">{error}</p>
              </div>
            </CardBody>
          </Card>
        </div>
      )}
      {success && (
        <div className="fixed bottom-4 right-4 z-50 animate-in slide-in-from-right-full">
          <Card className="border-green-600 bg-green-100 dark:border-green-400 dark:bg-green-900/50 shadow-lg">
            <CardBody className="p-4">
              <div className="flex items-center space-x-2 text-green-900 dark:text-green-200">
                <FiCheckCircle className="h-5 w-5 flex-shrink-0" />
                <p className="font-bold">{success}</p>
              </div>
            </CardBody>
          </Card>
        </div>
      )}

      {/* Main Upload Card */}
      <Card className="w-full lg:w-2/3 xl:w-1/2">
        <CardBody className="p-4">
          <button
            className={`border-2 border-dashed rounded-lg p-8 text-center transition-all duration-200 cursor-pointer ${
              isDragOver
                ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                : 'border-gray-500 hover:border-gray-400 dark:hover:border-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800/50'
            }`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                fileInputRef.current?.click()
              }
            }}
            type="button"
            aria-label="Click to select files or drag and drop files here"
            tabIndex={0}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              onChange={handleFileSelect}
              className="hidden"
              id="file-input"
              accept={ACCEPTED_EXTENSIONS}
            />
            <FiUpload className="mx-auto h-16 w-16 sm:h-20 sm:w-20 text-gray-400 dark:text-gray-500 mb-6" />
            <h3 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-white mb-4">
              Drop files here or click to browse
            </h3>
            <p className="text-gray-500 dark:text-gray-400 text-sm">
              Valid formats: PDF, images, documents, and more • Max 200MB per
              file
            </p>
          </button>

          {/* File List Section */}
          {files.length > 0 && (
            <div className="mt-6">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  Selected Files ({files.length})
                </h4>
                <Button
                  size="sm"
                  variant="light"
                  onPress={clearAllFiles}
                  disabled={isUploading}
                  className="text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400"
                >
                  Clear All
                </Button>
              </div>
              <div className="max-h-80 overflow-y-auto border border-gray-300 dark:border-gray-600 rounded-lg p-2 space-y-1.5">
                {files.map(({ file, id }) => (
                  <div
                    key={id}
                    className="flex items-center justify-between p-1 bg-gray-100 dark:bg-black border border-gray-300 dark:border-gray-600 rounded-lg transition-colors hover:bg-gray-100 dark:hover:bg-gray-900 gap-4"
                  >
                    <FiFile className="h-6 w-6 text-gray-700 dark:text-gray-300 flex-shrink-0 m-2" />
                    <div className="flex w-full flex-row justify-between items-center">
                      <p className="text-black dark:text-white">{file.name}</p>
                      <p className="text-sm text-gray-700 dark:text-gray-300">
                        {formatFileSize(file.size)}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => removeFile(id)}
                      className="m-2 text-gray-700 hover:text-red-700 dark:text-gray-300 dark:hover:text-red-300 transition-colors rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 border"
                      disabled={isUploading}
                      aria-label={`Remove ${file.name}`}
                    >
                      <FiX className="h-5 w-5" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Upload Progress */}
          {isUploading && (
            <div className="mt-6">
              <Progress
                value={uploadProgress}
                className="w-full"
                color="success"
              />
              <p className="text-base text-gray-700 dark:text-gray-300 mt-3 text-center">
                Uploading files...
              </p>
            </div>
          )}

          {/* Upload Button */}
          <div className="mt-6 flex justify-center">
            <Button
              color="default"
              size="lg"
              radius="lg"
              onPress={handleUpload}
              disabled={files.length === 0 || isUploading}
              className="inline-flex cursor-pointer rounded-lg bg-black px-8 py-4 text-base font-bold text-white hover:bg-gray-800 focus:outline-none focus:ring-4 focus:ring-black/20 active:bg-black/90 disabled:bg-gray-300 disabled:text-gray-500 transition-all duration-200 transform hover:scale-105"
            >
              {isUploading
                ? 'Uploading...'
                : `Upload ${files.length} File${files.length === 1 ? '' : 's'}`}
            </Button>
          </div>
        </CardBody>
      </Card>
    </div>
  )
}
