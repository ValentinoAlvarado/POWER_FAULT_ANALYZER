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
  fetch(`https://api.github.com/repos/${repository}/releases/latest`, { headers: { Accept: 'application/vnd.github+json' } })
    .then(response => { if (!response.ok) throw new Error(`No public release (${response.status})`); return response.json(); })
    .then(release => {
      const asset = (release.assets || []).find(item => item.name === 'PFA-Windows-x64.zip');
      if (!asset) throw new Error('The latest release does not contain PFA-Windows-x64.zip.');
      download.href = asset.browser_download_url;
      download.removeAttribute('aria-disabled');
      download.textContent = `Download for Windows · ${release.tag_name}`;
      note.textContent = `${release.name || release.tag_name} · ${new Date(release.published_at).toLocaleDateString()} · ZIP package`;
    })
    .catch(error => {
      download.textContent = 'No verified release available';
      download.setAttribute('aria-disabled', 'true');
      note.textContent = `${error.message}. Download links activate only after a published release includes the verified Windows asset.`;
    });
})();
