import { describe, expect, it } from 'vitest'

import { renderMarkdownToHtml } from '../utils/markdown'

describe('renderMarkdownToHtml', () => {
  it('renders headings, emphasis, and lists for ai messages', () => {
    const html = renderMarkdownToHtml(`## Title

- first
- **second**
`)

    expect(html).toContain('<h2>Title</h2>')
    expect(html).toContain('<ul>')
    expect(html).toContain('<li>first</li>')
    expect(html).toContain('<li><strong>second</strong></li>')
  })

  it('escapes unsafe html before rendering markdown', () => {
    const html = renderMarkdownToHtml('<script>alert(1)</script>\n\n`const x = 1`')

    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
    expect(html).toContain('<code>const x = 1</code>')
    expect(html).not.toContain('<script>')
  })

  it('treats model br and p tags as line breaks before markdown rendering', () => {
    const html = renderMarkdownToHtml('line1<br>line2<br/>line3<p>line4</p><div>line5</div>')

    expect(html).toContain('<p>line1<br />line2<br />line3</p>')
    expect(html).toContain('<p>line4</p>')
    expect(html).toContain('<p>line5</p>')
    expect(html).not.toContain('&lt;br')
  })

  it('renders markdown pipe tables from ai responses', () => {
    const html = renderMarkdownToHtml(`| Item | Value |
| --- | --- |
| Frequency | Monthly |
| Amount | 500 |`)

    expect(html).toContain('<div class="md-table-wrap"><table>')
    expect(html).toContain('<th>Item</th>')
    expect(html).toContain('<th>Value</th>')
    expect(html).toContain('<td>Monthly</td>')
    expect(html).toContain('<td>500</td>')
  })
})
