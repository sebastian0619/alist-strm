package cn.jackding.aliststrm;

import cn.jackding.aliststrm.config.Config;
import cn.jackding.aliststrm.service.StrmService;
import cn.jackding.aliststrm.tg.StrmBot;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.lang3.StringUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;
import org.telegram.telegrambots.bots.DefaultBotOptions;
import org.telegram.telegrambots.meta.TelegramBotsApi;
import org.telegram.telegrambots.meta.exceptions.TelegramApiException;
import org.telegram.telegrambots.updatesreceivers.DefaultBotSession;

@SpringBootApplication
@Slf4j
@EnableAsync
public class AlistStrmApplication implements CommandLineRunner {

    @Autowired
    private StrmService strmService;

    @Value("${runAfterStartup:1}")
    private String runAfterStartup;


    public static void main(String[] args) {
        SpringApplication.run(AlistStrmApplication.class, args);
    }

    @Override
    public void run(String... args) throws Exception {
        if ("1".equals(runAfterStartup)) {
            strmService.strm();
        }
        if (StringUtils.isBlank(Config.tgUserId) || StringUtils.isBlank(Config.tgToken)) {
            return;
        }
        TelegramBotsApi telegramBotsApi;
        try {
            telegramBotsApi = new TelegramBotsApi(DefaultBotSession.class);
        } catch (TelegramApiException e) {
            log.error("", e);
            return;
        }
        DefaultBotOptions botOptions = new DefaultBotOptions();
//        botOptions.setProxyHost(Config.telegramBotProxyHost);
//        botOptions.setProxyPort(Config.telegramBotProxyPort);
//        botOptions.setProxyType(DefaultBotOptions.ProxyType.HTTP);
        //使用AbilityBot创建的事件响应机器人
        try {
            telegramBotsApi.registerBot(new StrmBot(botOptions));
        } catch (TelegramApiException e) {
            log.error("", e);
        }
    }


}
