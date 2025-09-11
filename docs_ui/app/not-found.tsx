import { FaBan } from 'react-icons/fa6'

export default function Custom404() {
  return (
    <div className="h-40 w-40 flex flex-col items-center justify-center gap-3 bg-black text-white rounded-lg border dark:border-1.5 border-white ring-2 ring-black border-offset-1">
      <FaBan className="text-7xl" />
      <span className="text-2xl font-bold">Not Found</span>
    </div>
  )
}
