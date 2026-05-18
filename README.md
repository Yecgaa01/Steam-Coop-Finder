# Steam Coop Finder

A small desktop app for finding co-op games on Steam without digging through the store by hand.
It started as a personal tool for finding new games to play with friends, so the focus is simple: discover, filter, favorite, and open the Steam page when something looks interesting. This is still experimental and built mostly for personal discovery.

### Features:

* Discover Steam games by co-op type
* Filter imported games by:
  * Co-op type
  * Supported language
  * Genre/tag
  * Favorites
* Compact game details popup with:
  * Cover image
  * Developer/publisher
  * Steam review summary
  * Positive/negative review counts
  * Genres/categories
  * Full/current price when available
  * Steam page button
* Local SQLite cache
* Portuguese/English interface
* Batch import with pause/stop support

This app uses public Steam Store endpoints and stores data locally on your machine.

Please be gentle with Steam requests. Batch import includes delays and rate-limit handling, but large imports can still take a while.

Download the repository as a zip and run `build_portable.bat` to install it 
