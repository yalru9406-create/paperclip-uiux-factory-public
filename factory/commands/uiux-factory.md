# UI/UX Factory Commands

## Create A Run

```bash
yalru-uiux-factory new \
  --slug my-ui-job \
  --goal "Build the requested mobile product flow" \
  --target-repo "/absolute/path/to/repo" \
  --write-scope "src/**,app/**" \
  --approval-text "User approved this exact target_repo and write_scope for the run." \
  --screens 5 \
  --stack "React/Next.js" \
  --design-guide "/path/to/design-guide.pdf"
```

## Check Factory Health

```bash
yalru-uiux-factory doctor
```

## Check Latest Run

```bash
yalru-uiux-factory latest
yalru-uiux-factory status "$(yalru-uiux-factory latest)"
yalru-uiux-factory capture-evidence "$(yalru-uiux-factory latest)"
```
