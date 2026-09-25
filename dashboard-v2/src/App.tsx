import { useEffect } from 'react'
import { useScreens, useActiveScreen } from './stores/screensStore'
import { useFeeds } from './stores/feedsStore'
import { useUniverse } from './stores/universeStore'
import { useWatchlists } from './stores/watchlistsStore'
import { useSettings } from './stores/settingsStore'
import { useSetups } from './stores/setupsStore'
import { useCapabilities } from './stores/capabilitiesStore'
import { TopBar } from './components/TopBar'
import { Workspace } from './components/Workspace'

export default function App() {
  const loaded = useScreens(s => s.loaded)
  const loadError = useScreens(s => s.loadError)
  const screen = useActiveScreen()
  const menuHidden = useSettings(s => s.menuHidden)

  useEffect(() => {
    void useScreens.getState().load()
    void useUniverse.getState().load()
    void useWatchlists.getState().load()
    void useCapabilities.getState().load()
    void useSetups.getState().load()
    useFeeds.getState().connectAll()
    return () => useFeeds.getState().disconnectAll()
  }, [])

  return (
    <div className="app">
      <TopBar />
      <main className={`app-main${screen?.locked ? ' locked' : ''}${menuHidden ? ' menu-hidden' : ''}`}>
        {!loaded ? (
          <div className="wf-empty" style={{ height: '60vh' }}><b>Loading screens…</b></div>
        ) : screen ? (
          <>
            {loadError && (
              <div className="toast down" title={loadError}>
                Scanner did not answer /api/v2 ({loadError}). Layout changes are kept in this tab only until it does.
              </div>
            )}
            <Workspace screen={screen} />
          </>
        ) : (
          <div className="wf-empty" style={{ height: '60vh' }}><b>No screen</b><span>Use the Screen menu to create one.</span></div>
        )}
      </main>
    </div>
  )
}
