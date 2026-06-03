/**
 * Dashboard Socket.IO & Chart Responsiveness Fixes
 * Addresses:
 * 1. Socket.IO ping timeout issues  
 * 2. Chart responsiveness on mobile
 * 3. Proper chart resizing on window resize
 */

(function() {
    'use strict';

    // ═══════════════════════════════════════════════════════════════════
    // SOCKET.IO CONFIGURATION IMPROVEMENTS
    // ═══════════════════════════════════════════════════════════════════

    // Global socket configuration overrides
    const SOCKET_CONFIG = {
        // Increase ping interval to 45 seconds (default: 25s)
        // This gives more buffer before timeout
        pingInterval: 45000,
        
        // Increase ping timeout to 30 seconds (default: 20s)
        // Socket.IO will disconnect if no pong received within 30s
        pingTimeout: 30000,
        
        // Enable auto-reconnection
        reconnection: true,
        
        // Max reconnection attempts
        reconnectionAttempts: 10,
        
        // Initial reconnect delay (ms) - starts at 1s, increases exponentially
        reconnectionDelay: 1000,
        
        // Maximum reconnect delay (ms)
        reconnectionDelayMax: 10000,
        
        // Transports to try in order
        transports: ['websocket', 'polling'],
        
        // Enable protocol upgrade
        upgrade: true,
        
        // Force specific transport (remove to allow auto-selection)
        // forceNew: false,
        
        // Connection timeout
        timeout: 20000,
        
        // Include credentials for CORS
        withCredentials: true,
        
        // Enable manual pong handling
        autoConnect: true,
        
        // SocketIO protocol version
        protocolVersion: 4
    };

    // ═══════════════════════════════════════════════════════════════════
    // SOCKET.IO WRAPPER WITH ENHANCED ERROR HANDLING
    // ═══════════════════════════════════════════════════════════════════

    window.DashboardSocketManager = {
        socket: null,
        reconnectAttempts: 0,
        maxReconnectAttempts: 10,
        statusIndicator: null,
        isConnecting: false,

        /**
         * Initialize Socket.IO connection with improved error handling
         */
        init: function(retries = 0) {
            const self = this;

            // Wait for Socket.IO library to load
            if (typeof io === 'undefined') {
                if (retries < 100) {
                    return setTimeout(() => self.init(retries + 1), 100);
                }
                console.error('[Dashboard] Socket.IO library failed to load');
                return;
            }

            // Prevent multiple connection attempts
            if (self.socket || self.isConnecting) {
                return;
            }

            self.isConnecting = true;

            try {
                // Determine socket path based on URL structure
                const pathname = window.location.pathname || '';
                const parts = pathname.split('/').filter(Boolean);
                let socketPath = window.socketIoBasePath || '/socket.io';

                // Handle tenant-based paths
                if (!window.socketIoBasePath && parts.length >= 2 && parts[0] === 't') {
                    socketPath = `/${parts[0]}/${parts[1]}/socket.io`;
                }

                console.log('[Dashboard] Creating Socket.IO connection at:', socketPath);
                console.log('[Dashboard] Socket config:', SOCKET_CONFIG);

                // Create socket with improved configuration
                self.socket = io(window.location.origin, {
                    ...SOCKET_CONFIG,
                    path: socketPath
                });

                // Bind event handlers
                self.bindEventHandlers();

            } catch (err) {
                console.error('[Dashboard] Socket.IO initialization failed:', err);
                self.isConnecting = false;
            }
        },

        /**
         * Bind all Socket.IO event handlers
         */
        bindEventHandlers: function() {
            const self = this;
            const socket = self.socket;

            if (!socket) return;

            // ─── Connection Events ───
            socket.on('connect', function() {
                console.log('[Dashboard] Socket connected - ID:', socket.id);
                self.reconnectAttempts = 0;
                self.isConnecting = false;
                self.updateStatusIndicator('connected');
                
                // Emit join event to subscribe to updates
                try {
                    socket.emit('join', { room: 'dashboard' });
                    console.log('[Dashboard] Emitted join event');
                } catch (e) {
                    console.warn('[Dashboard] Join emit failed:', e);
                }
            });

            socket.on('connect_error', function(err) {
                console.error('[Dashboard] Connection error:', err);
                self.updateStatusIndicator('connecting');
            });

            socket.on('connect_timeout', function() {
                console.warn('[Dashboard] Connection timeout');
                self.updateStatusIndicator('connecting');
            });

            socket.on('disconnect', function(reason) {
                console.warn('[Dashboard] Socket disconnected -', reason);
                self.isConnecting = false;
                self.updateStatusIndicator('disconnected');

                // Attempt reconnection for specific reasons
                if (reason === 'ping timeout' || reason === 'transport error') {
                    console.log('[Dashboard] Attempting manual reconnection due to:', reason);
                    setTimeout(() => {
                        if (self.socket && !self.socket.connected) {
                            self.socket.connect();
                        }
                    }, 2000);
                }
            });

            socket.on('error', function(err) {
                console.error('[Dashboard] Socket error:', err);
            });

            socket.on('reconnect_attempt', function() {
                self.reconnectAttempts++;
                console.log(`[Dashboard] Reconnect attempt ${self.reconnectAttempts}/${self.maxReconnectAttempts}`);
                self.updateStatusIndicator('connecting');
            });

            socket.on('reconnect', function() {
                console.log('[Dashboard] Socket reconnected');
                self.reconnectAttempts = 0;
                self.updateStatusIndicator('connected');
            });

            socket.on('reconnect_error', function(err) {
                console.error('[Dashboard] Reconnection error:', err);
            });

            socket.on('reconnect_failed', function() {
                console.error('[Dashboard] Reconnection failed after', self.maxReconnectAttempts, 'attempts');
                self.updateStatusIndicator('disconnected');
            });

            // ─── Metrics Events ───
            socket.on('metrics_update', function(data) {
                if (typeof window.handleMetricsUpdate === 'function') {
                    try {
                        window.handleMetricsUpdate(data);
                    } catch (e) {
                        console.error('[Dashboard] Metrics handler error:', e);
                    }
                }
            });

            socket.on('screenshot_frame', function(data) {
                if (typeof window.handleScreenshotUpdate === 'function') {
                    try {
                        window.handleScreenshotUpdate(data);
                    } catch (e) {
                        console.error('[Dashboard] Screenshot handler error:', e);
                    }
                }
            });

            console.log('[Dashboard] All event handlers bound');
        },

        /**
         * Update visual connection status indicator
         */
        updateStatusIndicator: function(status) {
            if (!this.statusIndicator) {
                this.createStatusIndicator();
            }

            const indicator = this.statusIndicator;
            if (!indicator) return;

            indicator.classList.remove('connected', 'disconnected', 'connecting');
            indicator.classList.add(status);

            const title = {
                'connected': 'Live updates active',
                'disconnected': 'Reconnecting...',
                'connecting': 'Connecting...'
            }[status] || 'Status unknown';

            indicator.title = title;
            console.log(`[Dashboard] Status: ${title}`);
        },

        /**
         * Create and inject status indicator element
         */
        createStatusIndicator: function() {
            if (this.statusIndicator) return;

            const indicator = document.createElement('div');
            indicator.className = 'socket-status-indicator connected';
            indicator.id = 'socket-status-indicator';
            indicator.title = 'Live updates active';

            // Only add to DOM if it doesn't exist
            if (!document.getElementById('socket-status-indicator')) {
                document.body.appendChild(indicator);
            }

            this.statusIndicator = indicator;
        },

        /**
         * Manually trigger reconnection
         */
        reconnect: function() {
            if (this.socket) {
                this.socket.disconnect();
                setTimeout(() => {
                    if (this.socket) {
                        this.socket.connect();
                    }
                }, 1000);
            }
        },

        /**
         * Emit event to server
         */
        emit: function(event, data) {
            if (this.socket && this.socket.connected) {
                this.socket.emit(event, data);
                return true;
            }
            console.warn(`[Dashboard] Cannot emit "${event}" - socket not connected`);
            return false;
        },

        /**
         * Check connection status
         */
        isConnected: function() {
            return this.socket && this.socket.connected;
        }
    };

    // ═══════════════════════════════════════════════════════════════════
    // CHART RESPONSIVENESS MANAGER
    // ═══════════════════════════════════════════════════════════════════

    window.ChartResponsivityManager = {
        charts: [],
        resizeTimeout: null,
        debounceDelay: 300,

        /**
         * Register chart for auto-resizing
         */
        register: function(chart) {
            if (chart && this.charts.indexOf(chart) === -1) {
                this.charts.push(chart);
            }
        },

        /**
         * Unregister chart
         */
        unregister: function(chart) {
            const idx = this.charts.indexOf(chart);
            if (idx > -1) {
                this.charts.splice(idx, 1);
            }
        },

        /**
         * Resize all registered charts
         */
        resizeAll: function() {
            this.charts.forEach(chart => {
                try {
                    if (chart && typeof chart.resize === 'function') {
                        chart.resize();
                    }
                } catch (e) {
                    console.warn('[ChartManager] Resize error:', e);
                }
            });
        },

        /**
         * Handle window resize with debouncing
         */
        handleWindowResize: function() {
            clearTimeout(this.resizeTimeout);
            this.resizeTimeout = setTimeout(() => {
                this.resizeAll();
            }, this.debounceDelay);
        },

        /**
         * Initialize resize listener
         */
        init: function() {
            const self = this;
            window.addEventListener('resize', () => self.handleWindowResize());
            console.log('[ChartManager] Initialized with debounce delay:', this.debounceDelay, 'ms');
        }
    };

    // ═══════════════════════════════════════════════════════════════════
    // DOM READY INITIALIZATION
    // ═══════════════════════════════════════════════════════════════════

    document.addEventListener('DOMContentLoaded', function() {
        console.log('[Dashboard] Initializing Socket.IO and chart responsivity...');

        // Initialize Socket.IO with enhanced configuration
        window.DashboardSocketManager.init();

        // Initialize chart responsivity manager
        window.ChartResponsivityManager.init();

        // Handle orientation changes on mobile
        window.addEventListener('orientationchange', function() {
            console.log('[Dashboard] Orientation changed');
            setTimeout(() => {
                window.ChartResponsivityManager.resizeAll();
            }, 500);
        });

        console.log('[Dashboard] Initialization complete');
    });

    // ═══════════════════════════════════════════════════════════════════
    // PERIODIC HEALTH CHECK
    // ═══════════════════════════════════════════════════════════════════

    setInterval(function() {
        const manager = window.DashboardSocketManager;
        if (manager.socket && !manager.socket.connected && !manager.isConnecting) {
            console.warn('[Dashboard] Socket not connected, attempting reconnect...');
            manager.reconnect();
        }
    }, 30000); // Check every 30 seconds

    console.log('[Dashboard] Socket.IO & Chart Responsivity module loaded');

})();
