import { FaCircleNotch } from 'react-icons/fa6'

export default function Loading() {
  return (
    <div className="h-40 w-40 flex flex-col items-center justify-center gap-3 bg-black text-white rounded-lg border dark:border-1.5 border-white ring-2 ring-black border-offset-1">
      <FaCircleNotch className="text-7xl animate-spin" />
      <span className="text-2xl">Loading</span>
    </div>
  )
}
