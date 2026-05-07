"""
Windows Service Wrapper for Server Monitoring Agent
- Uses pywin32 to run agent as a Windows service
- Handles start, stop, graceful shutdown, restart on failure
"""
import win32serviceutil
import win32service
import win32event
import servicemanager
import os
import sys
import logging
import time

SERVICE_NAME = "ServerMonitorAgent"

class ServerMonitorService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = "Server Monitoring Agent"
    _svc_description_ = "Multi-tenant Server Monitoring Agent for Microsoft 365/SharePoint."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.running = True

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.running = False
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                              servicemanager.PYS_SERVICE_STARTED,
                              (self._svc_name_, ""))
        self.main()

    def main(self):
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        logging.basicConfig(filename=os.path.join(log_dir, 'service.log'),
                            level=logging.INFO,
                            format='[SERVICE] %(asctime)s %(levelname)s: %(message)s')
        while self.running:
            try:
                os.system(f"python main.py")
            except Exception as e:
                logging.error(f"Agent crashed: {e}")
            time.sleep(5)  # Restart on failure after short delay

if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(ServerMonitorService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(ServerMonitorService)