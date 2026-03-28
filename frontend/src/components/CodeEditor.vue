<template>
  <div ref="editorEl" class="code-editor-wrapper" :class="{ 'read-only': !editable }"></div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter, drawSelection, rectangularSelection, highlightSpecialChars } from '@codemirror/view'
import { EditorState } from '@codemirror/state'
import { python } from '@codemirror/lang-python'
import { defaultKeymap, indentWithTab, history, historyKeymap } from '@codemirror/commands'
import { syntaxHighlighting, HighlightStyle, indentOnInput, bracketMatching, foldGutter, foldKeymap } from '@codemirror/language'
import { tags } from '@lezer/highlight'

const props = defineProps({
  modelValue: { type: String, default: '' },
  editable: { type: Boolean, default: true },
  minHeight: { type: String, default: '350px' },
})

const emit = defineEmits(['update:modelValue'])

const editorEl = ref(null)
let view = null

// Suppress internal changes triggering watch
let internalUpdate = false

onMounted(() => {
  // Dark navy theme
  const navyTheme = EditorView.theme({
    '&': { fontSize: '12px', height: '100%', backgroundColor: '#080e1e', color: '#c5cee0' },
    '.cm-scroller': { overflow: 'auto', minHeight: props.minHeight, fontFamily: "'JetBrains Mono', 'Fira Code', 'SF Mono', 'Cascadia Code', ui-monospace, monospace" },
    '.cm-content': { minHeight: props.minHeight, caretColor: '#6ea8fe' },
    '.cm-cursor, .cm-dropCursor': { borderLeftColor: '#6ea8fe' },
    '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection': { backgroundColor: '#1c3a5e' },
    '.cm-panels': { backgroundColor: '#0d1224', color: '#c5cee0' },
    '.cm-panels.cm-panels-top': { borderBottom: '1px solid #1a2340' },
    '.cm-panels.cm-panels-bottom': { borderTop: '1px solid #1a2340' },
    '.cm-searchMatch': { backgroundColor: '#1a3a5c', outline: '1px solid #2a5a8c' },
    '.cm-searchMatch.cm-searchMatch-selected': { backgroundColor: '#264f78' },
    '.cm-activeLine': { backgroundColor: '#0d1326' },
    '.cm-selectionMatch': { backgroundColor: '#1a3050' },
    '&.cm-focused .cm-matchingBracket, &.cm-focused .cm-nonmatchingBracket': { backgroundColor: '#1a3050', outline: '1px solid #3a6090' },
    '.cm-gutters': { backgroundColor: '#060a18', color: '#3a4560', borderRight: '1px solid #121a32' },
    '.cm-activeLineGutter': { backgroundColor: '#0d1326', color: '#5a6a8a' },
    '.cm-foldPlaceholder': { backgroundColor: '#141c30', border: 'none', color: '#5a7aaa' },
    '.cm-tooltip': { border: '1px solid #1a2340', backgroundColor: '#0d1224' },
    '.cm-tooltip .cm-tooltip-arrow:before': { borderTopColor: '#1a2340', borderBottomColor: '#1a2340' },
    '.cm-tooltip .cm-tooltip-arrow:after': { borderTopColor: '#0d1224', borderBottomColor: '#0d1224' },
    '.cm-tooltip-autocomplete': { '& > ul > li[aria-selected]': { backgroundColor: '#1a2a4a', color: '#c5cee0' } },
    '&.cm-focused': { outline: 'none' },
  }, { dark: true })

  // Syntax highlighting — vibrant colors on navy
  const navyHighlight = HighlightStyle.define([
    { tag: tags.keyword, color: '#c678dd' },                        // purple — if, def, class, return, import
    { tag: tags.controlKeyword, color: '#c678dd' },                  // purple — for, while, try
    { tag: tags.definitionKeyword, color: '#c678dd' },               // purple — def, class
    { tag: tags.moduleKeyword, color: '#c678dd' },                   // purple — import, from
    { tag: tags.operatorKeyword, color: '#c678dd' },                 // purple — and, or, not, in
    { tag: tags.operator, color: '#56b6c2' },                        // cyan — +, -, =, ==
    { tag: tags.comment, color: '#5c6a7a', fontStyle: 'italic' },   // muted blue-grey
    { tag: tags.lineComment, color: '#5c6a7a', fontStyle: 'italic' },
    { tag: tags.blockComment, color: '#5c6a7a', fontStyle: 'italic' },
    { tag: tags.string, color: '#98c379' },                          // green
    { tag: tags.special(tags.string), color: '#98c379' },            // f-strings
    { tag: tags.number, color: '#d19a66' },                          // orange
    { tag: tags.integer, color: '#d19a66' },
    { tag: tags.float, color: '#d19a66' },
    { tag: tags.bool, color: '#d19a66' },                            // True/False
    { tag: tags.function(tags.variableName), color: '#61afef' },     // blue — function calls
    { tag: tags.function(tags.definition(tags.variableName)), color: '#61afef', fontWeight: '600' }, // blue bold — def name
    { tag: tags.definition(tags.variableName), color: '#e5c07b' },   // gold — variable definitions
    { tag: tags.variableName, color: '#c5cee0' },                    // light text — variables
    { tag: tags.propertyName, color: '#e06c75' },                    // red — .property
    { tag: tags.className, color: '#e5c07b', fontWeight: '600' },    // gold bold — class names
    { tag: tags.typeName, color: '#e5c07b' },                        // gold — type names
    { tag: tags.self, color: '#e06c75', fontStyle: 'italic' },       // red italic — self
    { tag: tags.null, color: '#d19a66' },                            // orange — None
    { tag: tags.atom, color: '#d19a66' },                            // orange — True, False, None
    { tag: tags.special(tags.variableName), color: '#e06c75' },      // red — __dunder__
    { tag: tags.meta, color: '#61afef' },                            // blue — decorators
    { tag: tags.punctuation, color: '#8090a8' },                     // muted — brackets, commas
    { tag: tags.bracket, color: '#8090a8' },
    { tag: tags.separator, color: '#8090a8' },
    { tag: tags.derefOperator, color: '#c5cee0' },                   // dot operator
  ])

  const extensions = [
    python(),
    navyTheme,
    syntaxHighlighting(navyHighlight),
    lineNumbers(),
    highlightActiveLine(),
    highlightActiveLineGutter(),
    highlightSpecialChars(),
    drawSelection(),
    bracketMatching(),
    foldGutter(),
    indentOnInput(),
    keymap.of([...defaultKeymap, ...historyKeymap, ...foldKeymap, indentWithTab]),
    history(),
    EditorState.readOnly.of(!props.editable),
  ]

  if (props.editable) {
    extensions.push(rectangularSelection())
    extensions.push(
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          internalUpdate = true
          emit('update:modelValue', update.state.doc.toString())
        }
      })
    )
  }

  view = new EditorView({
    state: EditorState.create({
      doc: props.modelValue || '',
      extensions,
    }),
    parent: editorEl.value,
  })
})

watch(() => props.modelValue, (newVal) => {
  if (internalUpdate) {
    internalUpdate = false
    return
  }
  if (view && newVal !== view.state.doc.toString()) {
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: newVal || '' },
    })
  }
})

onBeforeUnmount(() => {
  if (view) {
    view.destroy()
    view = null
  }
})
</script>

<style scoped>
.code-editor-wrapper {
  border-radius: 0.5rem;
  overflow: hidden;
  border: 1px solid #121a32;
  background-color: #080e1e;
}
.code-editor-wrapper :deep(.cm-editor) {
  border-radius: 0.5rem;
}
.code-editor-wrapper.read-only :deep(.cm-cursor) {
  display: none !important;
}
</style>
