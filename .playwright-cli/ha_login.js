async (page) => {
  const username = 'emoore';
  const password = 'ciristest1';
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  async function clickFirst(candidates) {
    for (const locator of candidates) {
      if (await locator.count()) {
        await locator.first().click();
        return true;
      }
    }
    return false;
  }

  await page.waitForLoadState('domcontentloaded');
  for (let i = 0; i < 40; i += 1) {
    const userField = page.locator('input[name="username"], input#username, input[type="text"]').first();
    const passField = page.locator('input[name="password"], input#password, input[type="password"]').first();
    if (await userField.count() && await passField.count()) {
      await userField.fill(username);
      await passField.fill(password);
      await clickFirst([
        page.getByRole('button', { name: /log in|sign in/i }),
        page.locator('button[type="submit"]'),
        page.locator('input[type="submit"]'),
        page.locator('mwc-button'),
        page.locator('ha-progress-button'),
        page.locator('ha-button'),
      ]);
      break;
    }
    await wait(500);
  }

  for (let i = 0; i < 60; i += 1) {
    const success = await page.locator('text=Connected!').count();
    if (success) {
      return {url: page.url(), body: await page.locator('body').innerText()};
    }

    const authClicked = await clickFirst([
      page.getByRole('button', { name: /authorize|allow/i }),
      page.locator('button[type="submit"]'),
      page.locator('mwc-button'),
      page.locator('ha-progress-button'),
      page.locator('ha-button'),
    ]);
    if (authClicked) {
      await page.waitForLoadState('networkidle').catch(() => null);
    }

    if (page.url().includes('/oauth/callback')) {
      await page.waitForLoadState('networkidle').catch(() => null);
      return {url: page.url(), body: await page.locator('body').innerText()};
    }
    await wait(500);
  }
  return {url: page.url(), body: await page.locator('body').innerText()};
}
