import { FiRefreshCw } from 'react-icons/fi'

export default function Previewing() {
  return (
    <div className="h-40 w-40 flex flex-col items-center justify-center gap-3 bg-black text-white rounded-lg border dark:border-1.5 border-white ring-2 ring-black border-offset-1">
      <FiRefreshCw className="text-7xl animate-spin [animation-duration:2s]" />
      <span className="text-2xl">Previewing</span>
    </div>
  )
}
