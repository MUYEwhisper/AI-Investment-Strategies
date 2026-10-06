const fs = require('node:fs')

function readWindowState(filename, displays) {
  const fallback = { width: 1440, height: 960, maximized: false }
  try {
    const state = JSON.parse(fs.readFileSync(filename, 'utf8'))
    if (![state.x, state.y, state.width, state.height].every(Number.isFinite)) return fallback
    const visible = displays.some(({ workArea: area }) =>
      state.x < area.x + area.width - 100 && state.x + state.width > area.x + 100 &&
      state.y >= area.y && state.y < area.y + area.height - 100)
    if (!visible) return fallback
    const area = displays.find(({ workArea: area }) =>
      state.x >= area.x && state.x < area.x + area.width)?.workArea ?? displays[0].workArea
    return {
      x: Math.max(area.x, Math.min(state.x, area.x + area.width - 100)),
      y: state.y,
      width: Math.min(area.width, Math.max(960, state.width)),
      height: Math.min(area.height, Math.max(640, state.height)),
      maximized: state.maximized === true,
    }
  } catch {
    return fallback
  }
}

function saveWindowState(filename, window) {
  if (window.isMinimized() || window.isFullScreen()) return
  try {
    fs.writeFileSync(filename, JSON.stringify({ ...window.getNormalBounds(), maximized: window.isMaximized() }))
  } catch {
    // Read-only profiles should not prevent the application from closing.
  }
}

module.exports = { readWindowState, saveWindowState }
