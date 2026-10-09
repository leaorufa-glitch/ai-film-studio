import { test, expect } from '@playwright/test';

test('project → script → scene → world → shot → clip → approved Brief stays offline', async ({page}) => {
  await page.goto('/');
  await expect(page.getByRole('heading', {name:'让故事，成为电影。'})).toBeVisible();
  await page.getByRole('button', {name:'新建影片'}).click();
  await page.getByRole('dialog', {name:'新建影片'}).getByLabel('项目名称').fill('E2E 海边来信');
  await page.getByRole('dialog', {name:'新建影片'}).getByLabel('一句话想法 / 粘贴剧本').fill('海边的旧信');
  await page.getByRole('dialog', {name:'新建影片'}).getByRole('button', {name:'创建影片'}).click();
  await expect(page).toHaveURL(/\/01$/);
  await expect(page.getByRole('textbox', {name:'剧本正文'})).toHaveValue('海边的旧信');
  await page.getByRole('textbox', {name:'剧本正文'}).fill('第一场。她在海边读信。');
  await page.getByRole('button', {name:'保存版本'}).click();
  await expect(page.getByText('剧本新版本已保存')).toBeVisible();
  await page.getByRole('textbox', {name:'地点 / 时段'}).fill('清晨海边');
  await page.getByRole('textbox', {name:'这一场发生什么'}).fill('她读完旧信，决定离开。');
  await page.getByRole('button', {name:'新增场次'}).click();
  await page.getByRole('link', {name:'02 人物与世界'}).click();
  await page.getByRole('textbox', {name:'人物名称'}).fill('阿宁');
  await page.getByRole('textbox', {name:'身份说明'}).fill('年轻的旅人');
  await page.getByRole('button', {name:'添加身份'}).click();
  await page.getByRole('button', {name:/造型/}).click();
  await page.getByRole('combobox', {name:'所属人物'}).selectOption({label:'阿宁'});
  await page.getByRole('textbox', {name:'造型名称'}).fill('清晨外套');
  await page.getByRole('textbox', {name:'身份说明'}).fill('蓝色布外套');
  await page.getByRole('button', {name:'添加身份'}).click();
  await page.getByRole('button', {name:/场景/}).click();
  await page.getByRole('textbox', {name:'身份名称'}).fill('海边');
  await page.getByRole('textbox', {name:'身份说明'}).fill('浅色沙滩与灰蓝海面');
  await page.getByRole('button', {name:'添加身份'}).click();
  await page.getByRole('link', {name:'03 场次与分镜'}).click();
  await page.getByRole('textbox', {name:'观众看到什么'}).fill('她拿起旧信，读完后望向海面。');
  await page.getByRole('textbox', {name:'镜头目的'}).fill('决定离开');
  await page.getByRole('button', {name:'添加镜头'}).click();
  await expect(page.getByText('镜头已加入计划')).toBeVisible();
  await expect(page.getByText(/还需要补充.*表演.*摄影.*后才能确认/)).toBeVisible();
  await expect(page.getByRole('button', {name:'确认镜头'})).toBeDisabled();
  await page.getByRole('button', {name:'修改'}).click();
  await page.locator('.shot-edit').getByRole('textbox', {name:'动作过程'}).fill('她拿起信，读完后望向海面');
  await page.locator('.shot-edit').getByRole('textbox', {name:'表演'}).fill('呼吸放慢，目光坚定');
  await page.locator('.shot-edit').getByRole('textbox', {name:'摄影'}).fill('中近景，缓慢推进');
  await page.locator('.shot-edit').getByRole('textbox', {name:'声音'}).fill('海浪声和信纸声');
  await page.getByRole('button', {name:'保存修改'}).click();
  await page.getByRole('button', {name:'确认镜头'}).click();
  await page.getByRole('link', {name:'04 影片制作'}).click();
  await expect(page.getByText('请在服务端配置 DARL_API_KEY。')).toBeVisible();
  await page.getByRole('textbox', {name:'目标时长（秒）'}).fill('5');
  await page.getByRole('button', {name:'创建 Clip'}).click();
  await page.locator('.clip-summary').first().click();
  await expect(page.getByRole('heading', {name:'最终制作方案'})).toBeVisible();
  await expect(page.getByText('还没有制作方案。')).toBeVisible();
  await page.getByRole('combobox', {name:'映射镜头'}).selectOption({index:1});
  await page.getByRole('button', {name:'添加映射'}).click();
  await page.getByRole('button', {name:'编辑方案'}).click();
  await page.getByRole('textbox', {name:'这一段的目的'}).fill('她做出离开的决定');
  await page.getByRole('combobox', {name:'人物',exact:true}).selectOption({label:'阿宁'});
  await page.getByRole('combobox', {name:'造型',exact:true}).selectOption({index:1});
  await page.getByRole('combobox', {name:'场景身份'}).selectOption({label:'海边'});
  await page.getByRole('textbox', {name:'当前场景状态'}).fill('清晨，海面平静');
  await page.getByRole('textbox', {name:'片段开始时的实际状态'}).fill('阿宁手中拿着一封信');
  await page.getByRole('textbox', {name:'动作开始'}).fill('信封仍在手中');
  await page.getByRole('textbox', {name:'触发'}).fill('她注意到署名');
  await page.getByRole('textbox', {name:'发展'}).fill('展开信纸，读完后转头望海');
  await page.getByRole('textbox', {name:'结果'}).fill('把信收回');
  await page.getByRole('textbox', {name:'表演 · 可见细节'}).fill('呼吸放慢，目光抬起');
  await page.getByRole('textbox', {name:'摄影 · 景别与运动'}).fill('中近景，缓慢推进');
  await page.getByRole('textbox', {name:'声音'}).fill('海浪声与信纸声');
  await page.getByRole('textbox', {name:'计划结束状态'}).fill('阿宁决定离开，信仍在手中');
  await page.getByRole('button', {name:'保存新版本'}).click();
  await expect(page.getByText('方案已准备', {exact:true}).first()).toBeVisible();
  await expect(page.getByRole('button', {name:'生成一条'})).toBeDisabled();
});

test('station plan shows the real Brief without invented storyboard or media', async ({page}) => {
  await page.goto('/projects/station-film/04');
  await expect(page.getByText('请在服务端配置 DARL_API_KEY。')).toBeVisible();
  await page.getByRole('button', {name:/Clip A/}).click();
  await expect(page.getByRole('heading', {name:'最终制作方案'})).toBeVisible();
  await expect(page.getByText('镜头 1 0–3s', {exact:false})).toBeVisible();
  await expect(page.locator('.brief-readable')).not.toContainText('linxia');
  await expect(page.locator('.brief-readable')).not.toContainText('scene_initial');
  await expect(page.locator('.brief-readable')).not.toContainText('{');
  await expect(page.locator('.clip-status-grid').first()).toContainText('模型服务未配置');
  await page.getByRole('link', {name:'05 审片'}).click();
  await expect(page.getByText('测试结果或媒体不可播放')).toBeVisible();
  await expect(page.locator('video')).toHaveCount(0);
});

test('TEST ONLY Take needs human selection and actual-state confirmation before timeline', async ({page}) => {
  await page.goto('/projects/station-film/05');
  await expect(page.getByText('TEST ONLY')).toBeVisible();
  await page.getByRole('button', {name:'采用这条'}).click();
  await expect(page.getByText('已采用此 Take')).toBeVisible();
  await expect(page.getByRole('combobox', {name:'希望 AI 帮什么'})).toHaveValue('review_observation');
  await expect(page.locator('.state-diff')).toContainText('林夏');
  await expect(page.locator('.state-diff')).not.toContainText('未在最终制作方案中填写');
  await page.getByRole('textbox', {name:'这条片段实际怎样结束？'}).fill('左手拿信，望向站台。');
  await page.getByRole('button', {name:'记录观察'}).click();
  await expect(page.getByText('实际结尾与计划不同，接受这个实际结果并让下一片段据此继续？')).toBeVisible();
  await expect(page.getByText('实际：左手拿信，望向站台。')).toBeVisible();
  await page.getByRole('button', {name:'接受实际结果'}).click();
  await expect(page.getByText('已确认')).toBeVisible();
  await page.getByRole('link', {name:'06 成片'}).click();
  await page.getByRole('button', {name:/加入/}).first().click();
  await expect(page.getByText('影片序列')).toBeVisible();
  await expect(page.locator('.timeline-block')).toHaveCount(1);
  await expect(page.getByRole('button', {name:'导出预览'})).toBeDisabled();
  await expect(page.getByText(/TEST ONLY，不能导出正式预览/)).toBeVisible();
});

test('structured scene origin and 1024px workspace labels remain clear', async ({page}) => {
  await page.setViewportSize({width:1024,height:900});
  await page.goto('/projects/station-film/01');
  await expect(page.getByText('此项目由结构化场次创建，没有保留原始剧本文本。', {exact:false})).toBeVisible();
  await expect(page.getByRole('link', {name:'01 剧本'})).toBeVisible();
  await expect(page.getByRole('link', {name:'03 场次与分镜'})).toBeVisible();
  await expect(page.getByRole('link', {name:'04 影片制作'})).toBeVisible();
  await expect(page.locator('.sidebar-project-title')).toContainText('雨夜车站');
});

test('TEST ONLY contextual proposal requires human acceptance in 01 and 03', async ({page}) => {
  await page.goto('/projects/station-film/01');
  await expect(page.getByText('TEST ONLY 场次提案：林夏望向列车灯。')).toBeVisible();
  await expect(page.locator('.scene-row')).toHaveCount(1);
  await page.locator('.proposal-box').getByRole('button', {name:'接受并写入'}).click();
  await expect(page.locator('.scene-row')).toHaveCount(2);
  await page.goto('/projects/station-film/03');
  await expect(page.getByText('TEST ONLY 观察决心')).toBeVisible();
  await expect(page.locator('.shot-card')).toHaveCount(5);
  await page.locator('.proposal-box').first().getByRole('button', {name:'接受并写入'}).click();
  await expect(page.locator('.shot-card')).toHaveCount(6);
  await expect(page.locator('.shot-card').last()).toContainText('待确认');
});

test('TEST ONLY image candidate is adopted explicitly and Clip proposal stays human gated', async ({page}) => {
  await page.goto('/projects/station-film/02');
  await expect(page.getByText('TEST ONLY 人物候选')).toBeVisible();
  await expect(page.locator('.asset-card')).toHaveCount(0);
  await page.locator('.candidate-card').getByRole('button', {name:'采用'}).click();
  await expect(page.locator('.candidate-card')).toContainText('已采用');
  await expect(page.locator('.asset-card')).toHaveCount(1);
  await page.goto('/projects/station-film/04');
  await expect(page.locator('.proposal-box').first()).toContainText('TEST ONLY Clip 提案');
  await expect(page.locator('.clip-panel')).toHaveCount(4);
  await page.locator('.proposal-box').first().getByRole('button', {name:'接受并写入'}).click();
  await expect(page.locator('.clip-panel')).toHaveCount(5);
  await expect(page.getByText('请在服务端配置 DARL_API_KEY。')).toBeVisible();
});

test('independent Admin shows provider, failed job and media without a key', async ({page}) => {
  await page.goto('/admin');
  await expect(page.getByRole('heading', {name:'运行管理台'})).toBeVisible();
  await expect(page.getByText('TEST ONLY QA 数据库', {exact:false})).toBeVisible();
  await expect(page.getByText('Darl H3')).toBeVisible();
  await page.getByRole('combobox', {name:'任务状态筛选'}).selectOption('failed');
  await expect(page.getByText('job-e2e-failed-test-only')).toBeVisible();
  await expect(page.getByText('TEST ONLY', {exact:true}).first()).toBeVisible();
  await expect(page.locator('body')).not.toContainText(/sk-[A-Za-z0-9]{20,}/);
});

for (const selfHosted of [true, false]) {
  test(`Darl route is explicit with self-hosted availability ${selfHosted}`, async ({page}) => {
    await page.route('**/api/providers', async route => {
      const response = await route.fetch();
      const data = await response.json();
      await route.fulfill({response, json:{...data, h3:'可用', provider:'darl',
        execution_model:selfHosted?'MiniMax-H3':'runninghub-minimax-h3',
        execution_route:selfHosted?'自建 H3':'云端 H3 · 备用',
        self_hosted_h3:selfHosted?'可用':'服务未启动', cloud_h3:'可用'}});
    });
    await page.route('**/api/projects/station-film/jobs', route => route.fulfill({json:[]}));
    await page.route('**/api/projects/station-film/clips/A/generate?**', route => route.fulfill({
      json:{job:{id:'TEST-ONLY-route-job'}, expected_minutes:3}
    }));
    await page.goto('/projects/station-film/04');
    await page.getByRole('button', {name:/Clip A/}).click();
    await expect(page.locator('.execution-route')).toContainText(selfHosted?'自建 H3':'云端 H3 · 备用');
    await expect(page.getByRole('combobox', {name:'本次视频服务'})).toHaveCount(0);
    const requestPromise = page.waitForRequest(request => request.method()==='POST' && request.url().includes('/clips/A/generate?'));
    await page.getByRole('button', {name:'生成一条', exact:true}).click();
    const request = await requestPromise;
    expect(new URL(request.url()).searchParams.has('provider')).toBe(false);
    expect(new URL(request.url()).searchParams.has('execution_model')).toBe(false);
  });
}

test('TEST ONLY technical retry keeps frozen cloud model despite current self-hosted route', async ({page}) => {
  await page.route('**/api/providers', async route => {
    const response = await route.fetch();
    const data = await response.json();
    await route.fulfill({response, json:{...data, h3:'可用', execution_model:'MiniMax-H3',
      execution_route:'自建 H3', self_hosted_h3:'可用', cloud_h3:'可用'}});
  });
  await page.route('**/api/projects/station-film/jobs', route => route.fulfill({json:[{
    id:'TEST-ONLY-original-failed-job', status:'failed',
    metadata:{provider:'darl', error_category:'NETWORK_ERROR'},
    snapshot:{task:{clip_id:'A', task_mode:'MULTI_SHOT_ONE_PASS', source_brief:{id:'brief:A', version:1},
      provider:'darl', model_profile:{id:'h3-darl-cloud',version:1},
      target_model:'runninghub-minimax-h3', execution_model:'runninghub-minimax-h3'},
      cost_estimate:{provider:'darl'}}
  }]}));
  await page.route('**/api/projects/station-film/clips/A/readiness', route => route.fulfill({
    json:{status:'NOT_READY', reasons:[{code:'MISSING_FIELD', field:'purpose'}], brief_version:2}
  }));
  await page.route('**/api/projects/station-film/clips/A/generate?**', route => route.fulfill({
    json:{job:{id:'TEST-ONLY-retry-job'}, expected_minutes:3}
  }));
  await page.goto('/projects/station-film/04');
  await page.getByRole('button', {name:/Clip A/}).click();
  await expect(page.getByText('技术重试固定使用原路线：云端 H3 · 备用', {exact:false})).toBeVisible();
  const retry = page.getByRole('button', {name:'技术重试一条'});
  await expect(retry).toBeEnabled();
  const requestPromise = page.waitForRequest(request => request.method()==='POST' && request.url().includes('/clips/A/generate?'));
  await retry.click();
  const request = await requestPromise;
  const parameters = new URL(request.url()).searchParams;
  expect(parameters.get('retry_of')).toBe('TEST-ONLY-original-failed-job');
  expect(parameters.has('provider')).toBe(false);
  expect(parameters.has('creative_reason')).toBe(false);
});

test('TEST ONLY frozen self-hosted retry is disabled when only cloud route is available', async ({page}) => {
  await page.route('**/api/providers', route => route.fulfill({json:{h3:'可用', provider:'darl',
    execution_model:'runninghub-minimax-h3', execution_route:'云端 H3 · 备用',
    self_hosted_h3:'服务未启动', cloud_h3:'可用'}}));
  await page.route('**/api/projects/station-film/jobs', route => route.fulfill({json:[{
    id:'TEST-ONLY-local-failed-job', status:'failed', metadata:{provider:'darl',error_category:'NETWORK_ERROR'},
    snapshot:{task:{clip_id:'A', provider:'darl', model_profile:{id:'h3-darl',version:1},
      target_model:'MiniMax-H3', execution_model:'MiniMax-H3'}, cost_estimate:{provider:'darl'}}
  }]}));
  await page.goto('/projects/station-film/04');
  await page.getByRole('button', {name:/Clip A/}).click();
  await expect(page.locator('.execution-route')).toContainText('云端 H3 · 备用');
  await expect(page.getByText('技术重试固定使用原路线：自建 H3', {exact:false})).toBeVisible();
  await expect(page.getByRole('button', {name:'技术重试一条'})).toBeDisabled();
});

test('TEST ONLY legacy jobs stay read-only in Creator and Admin', async ({page}) => {
  const legacy = 'runninghub-minimax-h3'.split('-')[0];
  await page.route('**/api/projects/station-film/jobs', route => route.fulfill({json:[{
    id:'TEST-ONLY-legacy-job', status:'failed', metadata:{provider:legacy,error_category:'NETWORK_ERROR'},
    snapshot:{task:{clip_id:'A',model_profile:{id:'h3-'+legacy,version:1}},cost_estimate:{provider:legacy}}
  }]}));
  await page.route('**/api/admin/jobs*', route => route.fulfill({json:[{
    id:'TEST-ONLY-legacy-job', status:'failed',provider:legacy,legacy_provider:true,
    project_id:'station-film',clip_id:'A',task_id:'TEST-ONLY-legacy-task',error_category:'NETWORK_ERROR'
  }]}));
  await page.goto('/projects/station-film/04');
  await page.getByRole('button', {name:/Clip A/}).click();
  await expect(page.getByText('旧 Provider 任务仅供历史查看，不能技术重试。')).toBeVisible();
  await expect(page.getByRole('button', {name:'技术重试一条'})).toHaveCount(0);
  await page.goto('/admin');
  await expect(page.getByText('旧 Provider · 只读')).toBeVisible();
  await expect(page.getByRole('button', {name:'技术重试',exact:true})).toHaveCount(0);
  await expect(page.getByText('Darl H3',{exact:true})).toBeVisible();
  await expect(page.getByText(legacy+' H3', {exact:true})).toHaveCount(0);
  await expect(page.getByText('自建 H3 · 服务未启动',{exact:false})).toBeVisible();
  await expect(page.getByText('云端 H3 · 备用 · 未配置',{exact:false})).toBeVisible();
});
