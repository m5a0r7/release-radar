import { LogOut, Monitor, Moon, Sun } from 'lucide-react'
import { useNavigate } from 'react-router'

import { useMe, useSignOut } from '../api/hooks'
import { Crumb, PageHeader } from '../components/AppShell'
import { Avatar, Button, Card, CardTitle, ErrorNotice } from '../components/ui'
import { cn } from '../lib/cn'
import { useTheme, type Theme } from '../lib/theme'

const THEMES: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: 'system', label: 'System', icon: Monitor },
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'dark', label: 'Dark', icon: Moon },
]

export function SettingsPage() {
  const me = useMe()
  const signOut = useSignOut()
  const navigate = useNavigate()
  const [theme, setTheme] = useTheme()
  const user = me.data?.user

  return (
    <>
      <PageHeader crumbs={<Crumb>Settings</Crumb>} />
      <main className="flex-1 p-6">
        <div className="mx-auto max-w-2xl space-y-6">
          <h1 className="text-xl font-semibold tracking-tight">Settings</h1>

          <Card className="p-5">
            <CardTitle>Account</CardTitle>
            {user && (
              <div className="mt-4 flex items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <Avatar name={user.name} url={user.avatar_url} className="size-10" />
                  <div className="text-sm">
                    <p className="font-medium">{user.name}</p>
                    <p className="text-zinc-500">
                      {user.email ??
                        (user.provider === 'github' ? 'GitHub account' : 'Demo account')}
                      {' · '}
                      {me.data?.workspace.name}
                    </p>
                  </div>
                </div>
                <Button
                  variant="secondary"
                  disabled={signOut.isPending}
                  onClick={() =>
                    signOut.mutate(undefined, {
                      onSuccess: () => navigate('/login', { replace: true }),
                    })
                  }
                >
                  <LogOut className="size-4" />
                  Sign out
                </Button>
              </div>
            )}
            {signOut.error && (
              <div className="mt-3">
                <ErrorNotice error={signOut.error} />
              </div>
            )}
          </Card>

          <Card className="p-5">
            <CardTitle>Appearance</CardTitle>
            <div className="mt-4 grid grid-cols-3 gap-2" role="radiogroup" aria-label="Theme">
              {THEMES.map(({ value, label, icon: Icon }) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={theme === value}
                  onClick={() => setTheme(value)}
                  className={cn(
                    'flex items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm',
                    theme === value
                      ? 'border-blue-600 bg-blue-50 font-medium text-blue-700 dark:bg-blue-500/10 dark:text-blue-400'
                      : 'border-zinc-200 hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800',
                  )}
                >
                  <Icon className="size-4" />
                  {label}
                </button>
              ))}
            </div>
          </Card>
        </div>
      </main>
    </>
  )
}
