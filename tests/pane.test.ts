import { expect, test } from 'claude-code/testing'

const PANE_PROPS = {
  title: 'eqlens',
  isFocused: true,
  bodyColumns: 80,
  placement: 'dock' as const,
  scroll: { offset: 0, bodyRows: 30 },
  view: {},
}

const PNG = '/tmp/eqlens-pane/a.png'

function pngHeader(width: number, height: number) {
  const u32 = (value: number) => [(value >>> 24) & 255, (value >>> 16) & 255, (value >>> 8) & 255, value & 255]
  const bytes = [137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82, ...u32(width), ...u32(height)]
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
  let out = ''
  for (let i = 0; i < bytes.length; i += 3) {
    const triple = (bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2]
    out += alphabet[(triple >> 18) & 63] + alphabet[(triple >> 12) & 63] + alphabet[(triple >> 6) & 63] + alphabet[triple & 63]
  }
  return out
}

function stub(
  on,
  {
    entries = [] as { path: string; generation: number; tex: string; width?: number; height?: number }[],
    eqlens = { exitCode: 0, stdout: PNG + '\n', stderr: '' } as
      | { exitCode: number; stdout: string; stderr: string }
      | { missing: true },
    taken = false,
    term = 'xterm-kitty',
    cells = '',
  } = {},
) {
  const saved: { key: string; value: unknown }[] = []
  const argv: string[][] = []
  on('store.get', (_$, e) => ({ value: e.key === 'entries' ? entries : e.key === 'index' ? 0 : undefined }))
  on('store.set', (_$, e) => {
    saved.push({ key: e.key, value: e.value })
    return { value: undefined }
  })
  on('command.register', () => ({ value: undefined }))
  on('tool.register', () => {
    if (taken) throw new Error('the session already has an MCP server named "eqlens"')
    return { value: { tool: 'mcp__eqlens__show' } }
  })
  if (taken) on('tool.call', () => ({ result: 'drawn by the server' }))
  on('fs.exists', () => ({ value: true }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 12, mtimeMs: 1700000000000, isLink: false } }))
  on('fs.read', () => ({ value: { base64: pngHeader(800, 100) } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.invalidate', () => ({ value: undefined }))
  on('ui.render', () => ({ type: 'Text', props: {}, children: [''] }))
  on('session.start', () => ({ cwd: '/work' }))
  on('clock.now', () => ({ value: 1700000000000 }))
  on('env.get', (_$, e) => ({ value: e.name === 'HOME' ? '/Users/ada' : e.name === 'TERM' ? term : '' }))
  on('process.run', (_$, e) => {
    argv.push([...e.argv])
    if (e.argv[0] === 'mkdir') return { value: { exitCode: 0, stdout: '', stderr: '' } }
    if (cells && e.argv.includes('cells')) return { value: { exitCode: 0, stdout: cells, stderr: '' } }
    if ('missing' in eqlens && e.argv[0] === 'eqlens') return { deny: 'not found' }
    if ('missing' in eqlens) return { value: { exitCode: 0, stdout: PNG + '\n', stderr: '' } }
    return { value: eqlens }
  })
  return { saved, argv }
}

async function start($) {
  await $.session.start({ surface: 'terminal', isInteractive: true, cwd: '/work' })
}

async function pane($) {
  return $.ui.mount({
    plugin: 'eqlens',
    surface: 'terminal',
    requestId: 'eqlens',
    component: 'Pane',
    props: PANE_PROPS,
  })
}

test('opens with no formula', async ($, on) => {
  stub(on)
  await start($)
  const ui = await pane($)
  expect(await ui.find({ type: 'Text', text: /No formula yet/ })).toBeDefined()
  await ui.unmount()
})

test('draws a formula and shows that file', async ($, on) => {
  const { saved, argv } = stub(on)
  await start($)
  const result = await $.command.run({ command: 'eqlens', args: 'e^{i\\pi}+1=0' })
  expect(result.text).toBe('Drew e^{i\\pi}+1=0')
  const draw = argv.find((row) => row[0] === 'eqlens')
  expect(draw).toContain('--local')
  expect(draw).toContain('--')
  expect(draw?.[draw.length - 1]).toBe('e^{i\\pi}+1=0')

  const stored = saved.find((row) => row.key === 'entries')
  expect(stored?.value).toEqual([
    {
      path: PNG,
      generation: 1700000000000,
      tex: 'e^{i\\pi}+1=0',
      legend: false,
      notes: [],
      defines: [],
      tiers: [],
      width: 800,
      height: 100,
    },
  ])

  const ui = await pane($)
  const image = await ui.find({ key: 'view' })
  expect(image?.props.source).toEqual({ file: PNG, format: 'png', generation: 1700000000000 })
  expect(image?.props.columns).toBe(80)
  expect(image?.props.rows).toBe(5)
  await ui.unmount()
})

test('forwards legend and notes, and strips one pair of dollars', async ($, on) => {
  const { argv } = stub(on)
  await start($)
  const result = await $.command.run({
    command: 'eqlens',
    args: "--legend --note 'Q looks.' '$x=1$'",
  })
  expect(result.text).toBe('Drew x=1')
  const draw = argv.find((row) => row[0] === 'eqlens')
  expect(draw).toEqual([
    'eqlens',
    '--local',
    '-o',
    draw?.[3],
    '--legend',
    '--note',
    'Q looks.',
    '--',
    'x=1',
  ])
})

test('a bad formula is not kept', async ($, on) => {
  const { saved } = stub(on, { eqlens: { exitCode: 1, stdout: '', stderr: 'eqlens: unknown symbol\n' } })
  await start($)
  const result = await $.command.run({ command: 'eqlens', args: '\\begin{matrix}' })
  expect(result.text).toBe('eqlens: unknown symbol')
  expect(saved.some((row) => row.key === 'entries')).toBe(false)
})

test('refuses a flag the pane does not take', async ($, on) => {
  const { argv } = stub(on)
  await start($)
  const result = await $.command.run({ command: 'eqlens', args: '--color #fff x=1' })
  expect(result.text).toBe('The pane takes the formula, --legend, --define, --tier, and --note.')
  expect(argv.some((row) => row[0] === 'eqlens')).toBe(false)
})

test('drops the formula it is showing', async ($, on) => {
  stub(on, {
    entries: [{ path: PNG, generation: 1, tex: 'E=mc^2', width: 100, height: 20 }],
  })
  await start($)
  const result = await $.command.run({ command: 'eqlens', args: 'drop' })
  expect(result.text).toBe('Dropped E=mc^2')
  const ui = await pane($)
  expect(await ui.find({ type: 'Text', text: /No formula yet/ })).toBeDefined()
  expect(await ui.find({ key: 'view' })).toBeUndefined()
  await ui.unmount()
})

test('the show tool draws into the same pane', async ($, on) => {
  const { saved } = stub(on)
  await start($)
  const result = await $.tool.call({ tool: 'mcp__eqlens__show', tool_use_id: 'u1', tex: 'E=mc^2', legend: false })
  expect(result.result).toBe('Drew E=mc^2')
  const stored = saved.find((row) => row.key === 'entries')
  expect(Array.isArray(stored?.value) && stored.value[0].tex).toBe('E=mc^2')
})

test('uses ~/.local/bin/eqlens when the name is not on PATH', async ($, on) => {
  const { argv } = stub(on, { eqlens: { missing: true } })
  await start($)
  const result = await $.command.run({ command: 'eqlens', args: 'x=1' })
  expect(result.text).toBe('Drew x=1')
  expect(argv.some((row) => row[0] === '/Users/ada/.local/bin/eqlens')).toBe(true)
})

test('follows the eqlens MCP server when it holds the tool names', async ($, on) => {
  const { saved, argv } = stub(on, { taken: true })
  await start($)
  const typed = await $.command.run({ command: 'eqlens', args: 'x=1' })
  expect(typed.text).toBe('Drew x=1')
  const result = await $.tool.call({
    tool: 'mcp__eqlens__eqlens_render',
    tool_use_id: 'u2',
    tex: 'E=mc^2',
    define: ['E=energy'],
  })
  expect(result.result).toBe('drawn by the server')
  const draw = argv.filter((row) => row[0] === 'eqlens').pop()
  expect(draw).toContain('--define')
  expect(draw?.[draw.length - 1]).toBe('E=mc^2')
  const stored = saved.filter((row) => row.key === 'entries').pop()
  expect(Array.isArray(stored?.value) && stored.value.map((row) => row.tex)).toEqual(['x=1', 'E=mc^2'])
})

test('draws the formula in dots where the terminal cannot paint a picture', async ($, on) => {
  const cells = JSON.stringify({
    tex: 'x=1',
    picture: [[['⠰⠶', null], ['⢿⣿', '#3fb950']]],
    ledger: [{ glyph: 'x', color: '#3fb950', words: 'the unknown' }],
    notes: [],
    fits: true,
  })
  const { saved, argv } = stub(on, { term: 'xterm-256color', cells })
  await start($)
  const result = await $.command.run({ command: 'eqlens', args: 'x=1' })
  expect(result.text).toBe('Drew x=1')
  const asked = argv.find((row) => row.includes('cells'))
  expect(asked?.slice(0, 6)).toEqual(['eqlens', '--local', '--display', 'cells', '--columns', '58'])
  const stored = saved.filter((row) => row.key === 'entries').pop()
  expect(Array.isArray(stored?.value) && stored.value[0].cells.ledger[0].words).toBe('the unknown')
  const ui = await pane($)
  expect(await ui.find({ key: 'view' })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /⢿⣿/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /the unknown/ })).toBeDefined()
  await ui.unmount()
})
