// Results of an Admin maintenance run (POST /api/admin/system/maintenance/): counts only, never paths.
export type StepError = { error: true }
export type MaintenanceResults = {
  deletions?: { done: number; failed: number } | StepError
  index?: { indexed: number; failed: number } | StepError
  images?: { removed: number; bytes: number } | StepError
  storage?: { checked: number; missing: number; unreferenced: number } | StepError
}
export type MaintenanceRun = { at: string; actor: string | null; results: MaintenanceResults }
export type MaintenanceLine = { label: string; value: string; alert: boolean }

const units = ['B', 'KB', 'MB', 'GB', 'TB']
function size(value: number) {
  let amount = value, unit = 0
  while (amount >= 1024 && unit < units.length - 1) { amount /= 1024; unit++ }
  return `${amount.toFixed(unit && amount < 10 ? 1 : 0)} ${units[unit]}`
}
const failed = (step: object | undefined): step is StepError => !!step && 'error' in step

export function maintenanceLines(results: MaintenanceResults): MaintenanceLine[] {
  const lines: MaintenanceLine[] = []
  const { deletions, index, images, storage } = results
  if (deletions) lines.push(failed(deletions) ? { label: '檔案清理重試', value: '執行失敗', alert: true }
    : { label: '檔案清理重試', value: `完成 ${deletions.done} 件${deletions.failed ? `，仍失敗 ${deletions.failed} 件` : ''}`, alert: deletions.failed > 0 })
  if (index) lines.push(failed(index) ? { label: '補建搜尋索引', value: '執行失敗', alert: true }
    : { label: '補建搜尋索引', value: `${index.indexed} 份${index.failed ? `，失敗 ${index.failed} 份` : ''}`, alert: index.failed > 0 })
  if (images) lines.push(failed(images) ? { label: '清理未使用圖片', value: '執行失敗', alert: true }
    : { label: '清理未使用圖片', value: images.removed ? `${images.removed} 張（${size(images.bytes)}）` : '0 張', alert: false })
  if (storage) lines.push(failed(storage) ? { label: '一致性檢查', value: '執行失敗', alert: true }
    : {
        label: '一致性檢查',
        value: storage.missing || storage.unreferenced
          ? `${storage.checked} 個檔案：遺失 ${storage.missing}、多出 ${storage.unreferenced}`
          : `${storage.checked} 個檔案都一致`,
        alert: storage.missing > 0,
      })
  return lines
}

export const maintenanceSummary = (results: MaintenanceResults) =>
  maintenanceLines(results).map(line => `${line.label}：${line.value}`).join('；')
