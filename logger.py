from logging import Logger
import colorlog


handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
	'%(log_color)s%(asctime)s %(name)s [%(levelname)s] %(message)s'))

log: Logger = colorlog.getLogger("abode2rtc")
log.setLevel(colorlog.DEBUG)
log.addHandler(handler)

go2rtc_log: Logger = colorlog.getLogger('go2rtc')
go2rtc_log.setLevel(colorlog.DEBUG)
go2rtc_log.addHandler(handler)
