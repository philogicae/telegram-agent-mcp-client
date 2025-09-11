import { FaBan, FaCircleXmark } from 'react-icons/fa6'

export default function Restricted() {
  return (
    <div className="h-40 w-40 flex flex-col items-center justify-center gap-3 bg-black text-white rounded-lg border dark:border-1.5 border-white ring-2 ring-black border-offset-1">
      <div className="absolute top-2.5 right-2 flex flex-row h-8 w-28 rounded-lg items-center justify-center bg-black ring-2 ring-black border-offset-1">
        <div className="flex h-8 w-full rounded-lg border dark:border-1.5 border-white items-center justify-center pl-1 text-red-500">
          <FaCircleXmark className="text-sm" />
          <span className="text-xs font-mono tracking-tighter px-2">
            Blocked
          </span>
        </div>
      </div>
      <FaBan className="text-7xl" />
      <span className="text-2xl font-bold">Restricted</span>
    </div>
  )
}
