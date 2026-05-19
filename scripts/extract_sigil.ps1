$ErrorActionPreference = 'Stop'
function Get-DocxText([string]$path) {
    $zipCopy = Join-Path $env:TEMP ("docx-" + [guid]::NewGuid().ToString() + '.zip')
    $tmp = Join-Path $env:TEMP ("docx-" + [guid]::NewGuid().ToString())
    Copy-Item -LiteralPath $path -Destination $zipCopy -Force
    Expand-Archive -LiteralPath $zipCopy -DestinationPath $tmp -Force
    [xml]$doc = Get-Content -LiteralPath (Join-Path $tmp 'word\document.xml') -Encoding UTF8
    $nsMgr = [System.Xml.XmlNamespaceManager]::new($doc.NameTable)
    $nsMgr.AddNamespace('w', 'http://schemas.openxmlformats.org/wordprocessingml/2006/main')
    $nodes = $doc.SelectNodes('//w:t', $nsMgr)
    $sb = New-Object System.Text.StringBuilder
    foreach ($n in $nodes) {
        [void]$sb.Append($n.InnerText)
        [void]$sb.Append(' ')
    }
    Remove-Item $zipCopy -Force -ErrorAction SilentlyContinue
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    return ($sb.ToString() -replace '\s+', ' ').Trim()
}

$sigil = 'E:\project-infi\sigil.docx'
$out = 'E:\project-infi\scripts\sigil-extract.txt'
$text = Get-DocxText $sigil
$text | Set-Content -Path $out -Encoding UTF8
Write-Output "Wrote $($text.Length) chars to $out"
