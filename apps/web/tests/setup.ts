import { execFileSync } from 'child_process';
import path from 'path';
export default async function setup() {
  const root = path.resolve(__dirname, '../../..');
  execFileSync(path.join(root,'.venv/bin/python'), ['tests/seed_creator_e2e.py'], {
    cwd: root, env: { ...process.env,
      FILM_STUDIO_DB: path.join(root,'output/e2e/studio-test.sqlite'),
      FILM_STUDIO_MEDIA: path.join(root,'output/e2e/media') }, stdio: 'inherit' });
}
