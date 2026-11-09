# Hound Release Checklist (local prep done)
- [x] v0.3.0 tagged + GitHub Release created.
- [x] `python -m build` + `twine check dist/*` PASS (`dist/hound_browser_mcp-0.1.0*`).
- [x] Hosted waitlist issue template + CTA.
- [ ] **Bump version** in `pyproject.toml`/package metadata before next release (dist currently 0.1.0 name; align tag/versioning).
- [ ] PyPI upload (needs `TWINE_*` token): `.venv/bin/twine upload dist/*`
- [ ] Deploy 24/7 (Fly/Railway, free credits): set `HOUND_ADMIN_KEY`, `/data` volume, TLS. See `DEPLOY.md`.
- [ ] Add real checkout/waitlist URLs (Razorpay/Stripe/Gumroad/Tally) and push.
