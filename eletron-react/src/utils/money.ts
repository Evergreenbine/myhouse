const CN_NUMS = ['零', '壹', '贰', '叁', '肆', '伍', '陆', '柒', '捌', '玖']
const CN_RADICES = ['', '拾', '佰', '仟']
const CN_GROUPS = ['', '万', '亿', '兆']

function groupToChinese(value: number) {
  let text = ''
  let zeroPending = false
  for (let i = 3; i >= 0; i--) {
    const radix = Math.pow(10, i)
    const digit = Math.floor(value / radix) % 10
    if (digit === 0) {
      if (text) zeroPending = true
      continue
    }
    if (zeroPending) {
      text += CN_NUMS[0]
      zeroPending = false
    }
    text += CN_NUMS[digit] + CN_RADICES[i]
  }
  return text
}

function integerToChinese(value: number) {
  if (value === 0) return CN_NUMS[0]
  const groups: number[] = []
  let rest = value
  while (rest > 0) {
    groups.push(rest % 10000)
    rest = Math.floor(rest / 10000)
  }

  let text = ''
  let zeroPending = false
  for (let i = groups.length - 1; i >= 0; i--) {
    const group = groups[i]
    if (group === 0) {
      if (text) zeroPending = true
      continue
    }
    if (zeroPending || (text && group < 1000)) {
      text += CN_NUMS[0]
      zeroPending = false
    }
    text += groupToChinese(group) + CN_GROUPS[i]
  }
  return text
}

export function formatChineseMoney(value: number | string | null | undefined) {
  const numeric = Number(value || 0)
  if (!Number.isFinite(numeric)) return '零元整'
  const cents = Math.round(Math.abs(numeric) * 100)
  const integer = Math.floor(cents / 100)
  const jiao = Math.floor((cents % 100) / 10)
  const fen = cents % 10
  const sign = numeric < 0 ? '负' : ''
  let text = sign + integerToChinese(integer) + '元'
  if (jiao === 0 && fen === 0) return text + '整'
  if (jiao > 0) text += CN_NUMS[jiao] + '角'
  if (fen > 0) text += (jiao === 0 ? CN_NUMS[0] : '') + CN_NUMS[fen] + '分'
  return text
}
