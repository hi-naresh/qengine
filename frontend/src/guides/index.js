import performanceRaw from './performance.md?raw'
import tradesRaw from './trades.md?raw'
import riskRaw from './risk.md?raw'
import forexRaw from './forex.md?raw'
import hedgeRaw from './hedge.md?raw'
import monteCarloRaw from './monte-carlo.md?raw'
import stratQuickstartRaw from './strategy-quickstart.md?raw'
import stratMethodsRaw from './strategy-methods.md?raw'
import stratPropertiesRaw from './strategy-properties.md?raw'
import stratModesRaw from './strategy-modes.md?raw'
import stratIndicatorsRaw from './strategy-indicators.md?raw'
import stratImportsRaw from './strategy-imports.md?raw'

function parseMdGuide(raw) {
  const entries = {}
  const regex = /^## (\S+)\s*\n([\s\S]*?)(?=\n## |\s*$)/gm
  let match
  while ((match = regex.exec(raw)) !== null) {
    entries[match[1]] = match[2].trim()
  }
  return entries
}

export const guides = {
  performance: parseMdGuide(performanceRaw),
  trades: parseMdGuide(tradesRaw),
  risk: parseMdGuide(riskRaw),
  forex: parseMdGuide(forexRaw),
  hedge: parseMdGuide(hedgeRaw),
  'monte-carlo': parseMdGuide(monteCarloRaw),
  'strategy-quickstart': parseMdGuide(stratQuickstartRaw),
  'strategy-methods': parseMdGuide(stratMethodsRaw),
  'strategy-properties': parseMdGuide(stratPropertiesRaw),
  'strategy-modes': parseMdGuide(stratModesRaw),
  'strategy-indicators': parseMdGuide(stratIndicatorsRaw),
  'strategy-imports': parseMdGuide(stratImportsRaw),
}

// Flat lookup: all metric keys merged (monte-carlo last so MC-specific descriptions win)
export const allGuides = Object.assign(
  {},
  guides.performance,
  guides.trades,
  guides.risk,
  guides.forex,
  guides.hedge,
  guides['monte-carlo'],
)
