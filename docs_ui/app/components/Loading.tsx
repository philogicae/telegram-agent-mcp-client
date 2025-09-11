import { FaCircleNotch } from 'react-icons/fa6'

export default function Loading() {
  return (
    <div className="h-full w-full flex flex-col items-center justify-center gap-3 bg-black text-white">
      <FaCircleNotch className="text-7xl animate-spin" />
      <span className="text-2xl">Loading</span>
    </div>
  )
}
