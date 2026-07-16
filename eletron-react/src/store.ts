import { create } from 'zustand'

interface UIState {
  section: 'basic' | 'rent' | 'settings'
  sideBasic: 'buildings' | 'rooms' | 'tenants' | 'contracts' | 'water' | 'electric'
  sideRent: 'plan' | 'bills' | 'payments' | 'waterUsage' | 'electricUsage'
  selectedBuildingId: number | null
  planYear: number
  planMonth: number
  setSection: (s: UIState['section']) => void
  setSideBasic: (s: UIState['sideBasic']) => void
  setSideRent: (s: UIState['sideRent']) => void
  setSelectedBuildingId: (id: number | null) => void
  setPlanYearMonth: (year: number, month: number) => void
}

export interface BuildingOption {
  id: number
  rent_day?: number | string | null
}

const DAY_MS = 24 * 60 * 60 * 1000

// Choose the initial building from rent days and the current date.
export function getDefaultBuildingId(buildings: BuildingOption[], now = new Date()): number | null {
  if (!buildings.length) return null

  const ordered = buildings
    .map((building, index) => ({
      ...building,
      index,
      rentDay: Math.max(1, Number(building.rent_day) || 1),
    }))
    .sort((a, b) => a.rentDay - b.rentDay || a.index - b.index)

  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const currentDay = today.getDate()
  const currentCycleBuilding = ordered
    .filter(building => building.rentDay <= currentDay)
    .pop() || ordered[ordered.length - 1]

  // Show the earliest rent-day building during the three-day preparation window.
  const anchor = ordered[0]
  const currentMonthDays = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate()
  let anchorDate = new Date(
    today.getFullYear(),
    today.getMonth(),
    Math.min(anchor.rentDay, currentMonthDays),
  )
  if (anchorDate <= today) {
    const nextMonthDays = new Date(today.getFullYear(), today.getMonth() + 2, 0).getDate()
    anchorDate = new Date(
      today.getFullYear(),
      today.getMonth() + 1,
      Math.min(anchor.rentDay, nextMonthDays),
    )
  }

  const daysUntilAnchor = Math.ceil((anchorDate.getTime() - today.getTime()) / DAY_MS)
  if (daysUntilAnchor >= 0 && daysUntilAnchor <= 3) return Number(anchor.id)
  return Number(currentCycleBuilding.id)
}

// Keep the user's last selection; calculate a default only on first entry or invalid selection.
export function resolveBuildingId(buildings: BuildingOption[]): number | null {
  const selected = useUIStore.getState().selectedBuildingId
  if (selected != null && buildings.some(building => Number(building.id) === Number(selected))) {
    return Number(selected)
  }
  return getDefaultBuildingId(buildings)
}

export const useUIStore = create<UIState>((set) => ({
  section: 'basic',
  sideBasic: 'buildings',
  sideRent: 'plan',
  selectedBuildingId: null,
  planYear: new Date().getFullYear(),
  planMonth: new Date().getMonth() + 1,
  setSection: (s) => set({ section: s }),
  setSideBasic: (s) => set({ sideBasic: s }),
  setSideRent: (s) => set({ sideRent: s }),
  setSelectedBuildingId: (id) => set({ selectedBuildingId: id }),
  setPlanYearMonth: (year, month) => set({ planYear: year, planMonth: month }),
}))
