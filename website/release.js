(() => {
  const repository = document.documentElement.dataset.githubRepository || '';
  const download = document.getElementById('download');
  const source = document.getElementById('source');
  const sourceNav = document.getElementById('source-nav');
  const footer = document.getElementById('source-footer');
  const note = document.getElementById('release-note');
  if (!repository || repository.includes('YOUR_GITHUB_OWNER')) {
    download.textContent = 'Release not configured yet';
    download.setAttribute('aria-disabled', 'true');
    note.textContent = 'Before publishing this page, set data-github-repository in website/index.html to the public GitHub owner/repository.';
    return;
  }
  const repositoryUrl = `https://github.com/${repository}`;
  source.href = repositoryUrl;
  sourceNav.href = repositoryUrl;
  footer.href = repositoryUrl;
  fetch(`https://api.github.com/repos/${repository}/releases?per_page=30`, { headers: { Accept: 'application/vnd.github+json' } })
    .then(response => { if (!response.ok) throw new Error(`GitHub Releases request failed (${response.status})`); return response.json(); })
    .then(releases => {
      const release = releases.find(item => !item.draft && (item.assets || []).some(asset => asset.name === 'PFA-Setup-x64.exe'));
      if (!release) throw new Error('No published Windows installer is available yet.');
      const asset = (release.assets || []).find(item => item.name === 'PFA-Setup-x64.exe');
      download.href = asset.browser_download_url;
      download.removeAttribute('aria-disabled');
      download.textContent = `Install for Windows · ${release.tag_name}`;
      const channel = release.prerelease ? ' · Pre-release' : '';
      note.textContent = `${release.name || release.tag_name}${channel} · ${new Date(release.published_at).toLocaleDateString()} · Windows x64 setup · SHA-256 published with the release`;
    })
    .catch(error => {
      download.textContent = 'No verified release available';
      download.setAttribute('aria-disabled', 'true');
      note.textContent = `${error.message}. Download links activate only after a published release includes the verified Windows asset.`;
    });
})();
