// eqlens: draw a formula to a PNG and show that file in a pane.
// The terminal reads the file. This module keeps the path.

import { cellBox, cellsArgv, drawArgv, paints, parse, pngSize, screenCells, screenPng } from './formula.js'

const PANE = 'eqlens'
const STORE = 'entries'
const DIR = '/tmp/eqlens-pane'
const SHOW = 'mcp__eqlens__show'
const RENDER = 'mcp__eqlens__eqlens_render'

let entries = []
let index = 0
let note = ''
// False in a terminal that cannot paint a PNG: the pane then draws the formula in braille dots.
let pixels = true
let room = 60

export function register(on) {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'eqlens',
      description: 'Draw a formula and show it',
      argumentHint: '[formula | --legend | --define | --tier | --note | drop]',
      immediate: true,
    })
    // A session that runs the eqlens MCP server already owns the mcp__eqlens__ names.
    // The pane and the command still work: the pane then follows that server's drawings.
    try {
      await $.tool.register({
        name: 'show',
        description: 'Draw one mathtext formula and show the PNG in the eqlens pane.',
        inputSchema: {
          type: 'object',
          properties: {
            tex: { type: 'string', description: 'One formula. No preamble.' },
            legend: { type: 'boolean', description: 'Color Greek letters and add the English-name ledger.' },
            defines: {
              type: 'array',
              items: { type: 'string' },
              description: 'What a symbol means here, as KEY=meaning, for example "P=what one token can carry".',
            },
            tiers: {
              type: 'array',
              items: { type: 'string' },
              description: 'What a symbol is made of, as KEY=formula, for example "P=A_eA_e^\\top". Drawn under its row.',
            },
            notes: {
              type: 'array',
              items: { type: 'string' },
              description: 'Short fine-print lines under the formula.',
            },
          },
          required: ['tex'],
        },
      })
    } catch {
      // The server's eqlens_render stands in for the show tool.
    }
    pixels = await canPaint($)
    await load($)
    return next(e)
  })

  on('classic.SessionStart', { source: ['clear', 'resume', 'fork'] }, async ($, e, next) => {
    await load($)
    return next(e)
  })

  on('command.run', { command: 'eqlens' }, async ($, e) => {
    const text = await run($, e.args || '')
    await present($)
    return { text }
  })

  on('tool.call', { tool: SHOW }, async ($, e) => {
    const text = await draw($, jobFromTool(e))
    await present($)
    return { result: text }
  })

  on('tool.call', { tool: RENDER }, async ($, e, next) => {
    const result = await next(e)
    try {
      const input = e.input && typeof e.input === 'object' ? e.input : e
      if (input.format === undefined || input.format === 'png') {
        const job = jobFromTool({
          input: {
            tex: input.tex,
            legend: input.legend === true || input.brief === true,
            defines: input.define,
            tiers: input.tier,
            notes: input.notes,
          },
        })
        if (!job.error) {
          await draw($, job)
          await present($)
        }
      }
    } catch {
      // The server's answer stands whether or not the pane showed it.
    }
    return result
  })

  on('ui.render', { component: 'Pane' }, async ($, e, next) => {
    if (e.requestId !== PANE) return next(e)
    const { Box, Text, Button, Input, Image } = $.ui.resolve(e)
    const current = entries[index]
    if (e.props.bodyColumns > 0) room = e.props.bodyColumns
    const fitted = current ? cellBox(e.props.bodyColumns, current.width, current.height) : null
    const dots = current && e.surface === 'terminal' && !pixels && current.cells ? current.cells : null
    const picture = dots
      ? Box({ key: 'dots', flexDirection: 'column', children: dotLines(Text, dots) })
      : current && e.surface === 'terminal' && pixels && Image
        ? Image({
            key: 'view',
            source: { file: current.path, format: 'png', generation: current.generation },
            columns: fitted.columns,
            rows: fitted.rows,
            alt: current.tex.slice(0, 200),
          })
        : Text({ children: [current ? current.tex : 'No formula yet.'] })
    const where = current
      ? Text({ dimColor: true, children: [index + 1 + '/' + entries.length + '  ' + current.tex] })
      : Text({ dimColor: true, children: ['/eqlens e^{i\\pi}+1=0'] })
    return Box({
      flexDirection: 'column',
      gap: 1,
      children: [
        picture,
        where,
        ...(current ? [Text({ dimColor: true, children: [current.path] })] : []),
        ...(note ? [Text({ children: [note] })] : []),
        Box({
          flexDirection: 'row',
          columnGap: 2,
          children: [
            Button({ key: 'prev', label: 'Prev', plain: true, onPress: () => shift($, -1) }),
            Button({ key: 'next', label: 'Next', plain: true, onPress: () => shift($, 1) }),
            Button({ key: 'drop', label: 'Drop', plain: true, onPress: () => remove($) }),
          ],
        }),
        Input({
          key: 'draw',
          label: 'TeX',
          placeholder: 'e^{i\\pi}+1=0',
          value: '',
          submitLabel: 'draw',
          onSubmit: (value) => run($, value),
        }),
      ],
    })
  })
}

async function present($) {
  await fill($)
  const opened = await $.ui.open({ id: PANE, title: 'eqlens', focus: true, closeOnEscape: true, rows: 28 })
  // A narrow window holds the pane back until it is asked for.
  if (opened && opened.isPlaced === false) await $.ui.toast('eqlens drew it. Type /eqlens to see it.')
}

async function canPaint($) {
  const read = async (get) => {
    try {
      return (await get()) || ''
    } catch {
      return ''
    }
  }
  return paints({
    TERM: await read(() => $.env.get('TERM')),
    TERM_PROGRAM: await read(() => $.env.get('TERM_PROGRAM')),
    KITTY_WINDOW_ID: await read(() => $.env.get('KITTY_WINDOW_ID')),
  })
}

// The formula in dots, for the entry showing. Nothing to do where the terminal paints the PNG.
async function fill($) {
  const current = entries[index]
  if (pixels || !current || current.cells) return
  const found = await dotsFor($, current)
  if (!found) return
  current.cells = found
  await save($)
  $.ui.invalidate('ui.render')
}

async function dotsFor($, job) {
  const argv = cellsArgv(room - 2, { ...job, notes: job.notes || [] })
  const ran = await runEqlens($, argv.slice(1))
  if (ran.error || ran.exitCode !== 0) return null
  return screenCells(ran.stdout)
}

function dotLines(Text, cells) {
  const run = (text, color, key) => Text({ key, wrap: 'clip', ...(color ? { color } : {}), children: [text] })
  const lines = cells.picture.map((line, i) =>
    Text({ key: 'p' + i, wrap: 'clip', children: line.length ? line.map((part, j) => run(part[0], part[1], 'r' + j)) : [' '] }),
  )
  if (cells.ledger.length) lines.push(Text({ key: 'gap', children: [' '] }))
  const wide = Math.max(0, ...cells.ledger.map((row) => row.glyph.length))
  cells.ledger.forEach((row, i) =>
    lines.push(
      Text({ key: 'l' + i, children: [run(row.glyph.padEnd(wide + 2), row.color, 'g'), row.words] }),
    ),
  )
  cells.notes.forEach((line, i) => lines.push(Text({ key: 'n' + i, dimColor: true, children: [line] })))
  if (!cells.fits) lines.push(Text({ key: 'small', dimColor: true, children: ['Drawn small to fit. A wider pane draws it larger.'] }))
  return lines
}

async function load($) {
  const stored = await $.store.get(STORE)
  entries = Array.isArray(stored) ? stored.filter(isEntry) : []
  const storedIndex = await $.store.get('index')
  index = Number.isInteger(storedIndex) ? storedIndex : 0
  if (entries.length === 0) index = 0
  else if (index < 0 || index >= entries.length) index = 0
}

async function save($) {
  await $.store.set(STORE, entries)
  await $.store.set('index', index)
}

function isEntry(value) {
  return !!value && typeof value.path === 'string' && typeof value.tex === 'string' && Number.isInteger(value.generation)
}

function jobFromTool(event) {
  const input = event.input && typeof event.input === 'object' ? event.input : event
  const parsed = parse('-- ' + String(input.tex ?? ''))
  if (parsed.error || parsed.kind !== 'draw') return parsed.error ? parsed : { error: 'Give a formula.' }
  const raw = Array.isArray(input.notes) ? input.notes : typeof input.notes === 'string' ? [input.notes] : []
  const notes = raw.map((note) => String(note))
  if (notes.some((note) => note.trim() === '')) return { error: 'A --note needs a line.' }
  if (notes.length > 12) return { error: 'Too many notes.' }
  if (notes.some((note) => note.length > 500)) return { error: 'A note is too long.' }
  const defines = (Array.isArray(input.defines) ? input.defines : []).map((item) => String(item))
  if (defines.some((item) => !/^[^=]+=.*\S/.test(item))) return { error: 'A --define needs KEY=meaning.' }
  if (defines.length > 24) return { error: 'Too many definitions.' }
  if (defines.some((item) => item.length > 500)) return { error: 'A definition is too long.' }
  const tiers = (Array.isArray(input.tiers) ? input.tiers : []).map((item) => String(item))
  if (tiers.some((item) => !/^[^=]+=.*\S/.test(item))) return { error: 'A --tier needs KEY=formula.' }
  if (tiers.length > 24) return { error: 'Too many tiers.' }
  if (tiers.some((item) => item.length > 500)) return { error: 'A tier is too long.' }
  return { kind: 'draw', tex: parsed.tex, legend: input.legend === true, notes, defines, tiers }
}

async function run($, args) {
  const parsed = parse(args)
  if (parsed.error) return fail($, parsed.error)
  if (parsed.kind === 'open') {
    note = ''
    return entries.length ? entries.length + ' formula' + (entries.length === 1 ? '' : 's') + '.' : 'No formula yet.'
  }
  if (parsed.kind === 'drop') return remove($)
  return draw($, parsed)
}

async function draw($, job) {
  if (job.error) return fail($, job.error)
  if (!job.tex) return fail($, 'Give a formula.')
  const made = await $.process.run(['mkdir', '-p', DIR])
  if (!made || made.exitCode !== 0) return fail($, 'Could not write the PNG.')
  const stamp = await stampOf($)
  const out = DIR + '/' + stamp.toString(36) + '-' + Math.random().toString(36).slice(2, 8) + '.png'
  const argv = drawArgv(out, job)
  const ran = await runEqlens($, argv.slice(1))
  if (ran.error) return fail($, ran.error)
  if (ran.exitCode !== 0) {
    const detail = String(ran.stderr || ran.stdout || '').trim()
    return fail($, detail || 'The formula did not render.')
  }
  const screened = screenPng(ran.stdout)
  if (screened.error) return fail($, screened.error)
  const exists = await $.fs.exists(screened.path)
  if (!exists) return fail($, 'eqlens did not write a PNG.')
  const generation = await generationOf($, screened.path)
  const size = await measure($, screened.path)
  const entry = {
    path: screened.path,
    generation,
    tex: job.tex,
    legend: !!job.legend,
    notes: job.notes || [],
    defines: job.defines || [],
    tiers: job.tiers || [],
    width: size ? size.width : 0,
    height: size ? size.height : 0,
  }
  if (!pixels) {
    const found = await dotsFor($, entry)
    if (found) entry.cells = found
  }
  const found = entries.findIndex((item) => same(item, entry))
  if (found >= 0) {
    entries[found] = entry
    index = found
  } else {
    entries.push(entry)
    index = entries.length - 1
  }
  note = ''
  await save($)
  $.ui.invalidate('ui.render')
  return 'Drew ' + job.tex
}

async function runEqlens($, args) {
  const first = await tryRun($, ['eqlens', ...args])
  if (first.started) return first
  let home = ''
  try {
    home = (await $.env.get('HOME')) || ''
  } catch {
    home = ''
  }
  if (home) {
    const second = await tryRun($, [home.replace(/\/$/, '') + '/.local/bin/eqlens', ...args])
    if (second.started) return second
  }
  return { error: 'eqlens is not on PATH.' }
}

async function tryRun($, argv) {
  try {
    const ran = await $.process.run(argv, { timeoutMs: 60000 })
    return { started: true, exitCode: ran.exitCode, stdout: ran.stdout, stderr: ran.stderr }
  } catch {
    return { started: false }
  }
}

async function measure($, path) {
  try {
    const file = await $.fs.read(path, { as: 'bytes' })
    return pngSize(file && file.base64)
  } catch {
    return null
  }
}

async function stampOf($) {
  try {
    const now = await $.clock.now()
    if (Number.isFinite(now)) return Math.max(0, Math.floor(now))
  } catch {
    // Date.now still names a new file.
  }
  return Date.now()
}

async function generationOf($, path) {
  try {
    const stat = await $.fs.stat(path)
    if (stat && Number.isFinite(stat.mtimeMs)) return Math.max(0, Math.floor(stat.mtimeMs))
  } catch {
    // A missing stamp still shows the file. Drawing it again bumps the number.
  }
  return Date.now()
}

function same(entry, job) {
  const notes = Array.isArray(entry.notes) ? entry.notes : []
  const next = job.notes || []
  const defines = Array.isArray(entry.defines) ? entry.defines : []
  const nextDefines = job.defines || []
  return (
    entry.tex === job.tex &&
    !!entry.legend === !!job.legend &&
    notes.length === next.length &&
    notes.every((line, i) => line === next[i]) &&
    defines.length === nextDefines.length &&
    defines.every((item, i) => item === nextDefines[i]) &&
    JSON.stringify(Array.isArray(entry.tiers) ? entry.tiers : []) === JSON.stringify(job.tiers || [])
  )
}

async function shift($, by) {
  if (entries.length === 0) return
  index = (index + by + entries.length) % entries.length
  note = ''
  await save($)
  $.ui.invalidate('ui.render')
  await fill($)
}

async function remove($) {
  if (entries.length === 0) return fail($, 'No formula yet.')
  const gone = entries[index].tex
  entries.splice(index, 1)
  if (index >= entries.length) index = 0
  note = ''
  await save($)
  $.ui.invalidate('ui.render')
  return 'Dropped ' + gone
}

function fail($, text) {
  note = text
  $.ui.invalidate('ui.render')
  return text
}
