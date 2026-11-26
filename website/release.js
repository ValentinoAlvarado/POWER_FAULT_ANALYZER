(() => {
  const repository = document.documentElement.dataset.githubRepository || '';
  const installer = document.getElementById('download-installer');
  const portable = document.getElementById('download-portable');
  const sourceNav = document.getElementById('source-nav');
  const footer = document.getElementById('source-footer');
  const note = document.getElementById('release-note');
  const meta = document.getElementById('release-meta');
  const checksums = document.getElementById('checksums-link');
  const sbom = document.getElementById('sbom-link');
  const disable = (link) => link.setAttribute('aria-disabled', 'true');
  const enable = (link, href) => { link.href = href; link.removeAttribute('aria-disabled'); };

  if (!/^[^/]+\/[^/]+$/.test(repository)) {
    installer.textContent = 'Release not configured';
    note.textContent = 'The repository slug in the page configuration is invalid.';
    return;
  }
  const repoUrl = `https://github.com/${repository}`;
  sourceNav.href = repoUrl;
  footer.href = repoUrl;

  fetch(`https://api.github.com/repos/${repository}/releases?per_page=20`, {
    headers: { Accept: 'application/vnd.github+json' }, cache: 'no-store'
  })
    .then((response) => {
      if (!response.ok) throw new Error(`GitHub Releases API returned ${response.status}`);
      return response.json();
    })
    .then((releases) => {
      const release = releases.find((item) => {
        if (item.draft) return false;
        const names = new Set((item.assets || []).map((asset) => asset.name));
        return names.has('PFA-Setup-x64.exe') && names.has('SHA256SUMS.txt');
      });
      if (!release) throw new Error('No published release with a verified Windows installer is available yet.');
      const assets = new Map(release.assets.map((asset) => [asset.name, asset.browser_download_url]));
      enable(installer, assets.get('PFA-Setup-x64.exe'));
      installer.textContent = `Download Windows installer · ${release.tag_name}`;
      if (assets.has('PFA-Windows-x64.zip')) enable(portable, assets.get('PFA-Windows-x64.zip'));
      else disable(portable);
      if (assets.has('SHA256SUMS.txt')) enable(checksums, assets.get('SHA256SUMS.txt'));
      if (assets.has('SBOM.cdx.json')) enable(sbom, assets.get('SBOM.cdx.json'));
      const date = release.published_at ? new Date(release.published_at).toLocaleDateString() : 'date unavailable';
      meta.textContent = `Windows 10/11 · x64 · ${release.tag_name} · Published ${date} · GPL-3.0-or-later`;
      note.textContent = release.prerelease ? 'Preview release. Review the known limitations and checksums before use.' : 'Stable release. Verify SHA-256 before installation.';
    })
    .catch((error) => {
      installer.textContent = 'No verified Windows release yet';
      disable(installer);
      disable(portable);
      disable(checksums);
      disable(sbom);
      note.textContent = error.message;
    });
})();
