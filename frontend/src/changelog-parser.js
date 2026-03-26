/**
 * Parses CHANGELOG.md into structured data for the UI.
 * Imported at build time via Vite's ?raw, parsed at module load.
 */
import raw from '../../docs/CHANGELOG.md?raw'

function parseChangelog(md) {
  const versions = []
  const lines = md.split('\n')
  let current = null
  let currentSection = null

  for (const line of lines) {
    // Version header: ## [2.1.0] - 2026-03-26
    const versionMatch = line.match(/^## \[(.+?)\]\s*-\s*(.+)/)
    if (versionMatch) {
      current = { version: versionMatch[1], date: versionMatch[2].trim(), sections: [] }
      versions.push(current)
      currentSection = null
      continue
    }
    // Also match: ## [1.x] - Jesse Foundation
    const versionMatch2 = line.match(/^## \[(.+?)\]/)
    if (versionMatch2 && !current?.version?.startsWith(versionMatch2[1])) {
      current = { version: versionMatch2[1], date: line.replace(/^## \[.+?\]\s*-?\s*/, '').trim(), sections: [] }
      versions.push(current)
      currentSection = null
      continue
    }

    if (!current) continue

    // Section header: ### Section Name
    const sectionMatch = line.match(/^### (.+)/)
    if (sectionMatch) {
      currentSection = { title: sectionMatch[1], items: [] }
      current.sections.push(currentSection)
      continue
    }

    // Bold sub-header: **Sub Title** or **Sub Title** (`file`)
    const boldMatch = line.match(/^\*\*(.+?)\*\*(.*)/)
    if (boldMatch && currentSection) {
      const text = boldMatch[2].trim()
      if (text) {
        currentSection.items.push(`**${boldMatch[1]}** ${text}`)
      } else {
        // standalone bold header within section — treat as sub-label
        currentSection.items.push(`**${boldMatch[1]}**`)
      }
      continue
    }

    // Bullet items: - text
    const bulletMatch = line.match(/^- (.+)/)
    if (bulletMatch && currentSection) {
      currentSection.items.push(bulletMatch[1])
      continue
    }

    // Continuation of bullet (indented): starts with spaces after a bullet
    const contMatch = line.match(/^ {2,}(.+)/)
    if (contMatch && currentSection && currentSection.items.length > 0) {
      currentSection.items[currentSection.items.length - 1] += ' ' + contMatch[1].trim()
      continue
    }

    // Plain text paragraph (non-empty, not a separator)
    const trimmed = line.trim()
    if (trimmed && trimmed !== '---' && !trimmed.startsWith('#') && currentSection) {
      currentSection.items.push(trimmed)
    }
  }

  return versions
}

/** Parsed changelog versions array */
export const changelog = parseChangelog(raw)

/** Raw markdown text */
export const changelogRaw = raw

/**
 * Get a specific version's data
 * @param {string} version - e.g. '2.1.0'
 */
export function getVersion(version) {
  return changelog.find(v => v.version === version)
}

/**
 * Get the latest version entry
 */
export function getLatest() {
  return changelog[0]
}

/**
 * Flatten a version's sections into simple {title, desc} pairs for compact display.
 * Each section becomes one entry; items are joined.
 */
export function flattenVersion(version) {
  const v = typeof version === 'string' ? getVersion(version) : version
  if (!v) return []
  return v.sections.map(s => ({
    title: s.title,
    desc: s.items.slice(0, 3).map(i => i.replace(/\*\*(.+?)\*\*/g, '$1').replace(/`(.+?)`/g, '$1')).join('. '),
    fullItems: s.items,
  }))
}
