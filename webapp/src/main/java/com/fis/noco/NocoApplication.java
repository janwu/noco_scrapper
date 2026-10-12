package com.fis.noco;

import com.vaadin.flow.component.page.AppShellConfigurator;
import com.vaadin.flow.theme.Theme;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@Theme("noco-theme")
public class NocoApplication implements AppShellConfigurator {

    public static void main(String[] args) {
        SpringApplication.run(NocoApplication.class, args);
    }
}
