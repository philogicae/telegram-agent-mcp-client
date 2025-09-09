'use client'
import upload from '@services/upload'
import type { State } from '@utils/types'
import { useCallback } from 'react'
import { useNavigate } from 'react-router'

export default function useContinue() {
  const navigate = useNavigate()
  return useCallback(
    async (files: File[]): Promise<State> => {
      const res = await upload(files)
      if (!res) navigate('down')
      return res
    },
    [navigate]
  )
}
