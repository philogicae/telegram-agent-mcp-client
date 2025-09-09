'use client'
import { FaCircleNotch } from 'react-icons/fa6'

export default function Loading() {
  return (
    <div className="flex flex-col items-center justify-center w-full h-full gap-6">
      <FaCircleNotch className="text-6xl animate-spin" />
      <span className="text-3xl">Loading...</span>
    </div>
  )
}
